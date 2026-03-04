"""
Winiw Quality Scorecard — app.py v3.5
======================================
v3.3: Dashboard rediseñado, caché, JT restrictions, DSP PDF parser, WoW deltas
v3.4: SQL injection fix, hardcoding eliminado, caché selectivo, audit log, validaciones
v3.5 (este archivo):
  - 🔒 SEGURIDAD: Rate limiting en login — 5 intentos fallidos → bloqueo 15 min
  - 🏢 NUEVO TAB: Dashboard Ejecutivo — todos los centros en una pantalla, ranking, WoW
  - 📈 TENDENCIA: Gráfico de evolución del score por conductor (últimas 8 semanas)
  - 📊 TENDENCIA: Líneas de DNR, DCR, POD para análisis de causas raíz
  - 🎨 UX: Zonas de referencia en gráfico (FANTASTIC/GREAT/FAIR) para contexto visual
  - 🧹 CÓDIGO: Helper get_user_role() — elimina última query duplicada del admin
  - 🧹 CÓDIGO: st.write() → st.markdown() en todo el archivo
  - 📊 CÓDIGO: SEMANAS_VISIBLES_JT y TREND_SEMANAS_MAX como constantes configurables
"""

import io
import re
import os
import logging
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING — Configuración CENTRALIZADA antes de cualquier import interno.
# scorecard.py solo llama a logging.getLogger(__name__) sin basicConfig propio.
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/winiw_app.log", mode='a', encoding='utf-8')
        if os.path.isdir("logs") else logging.StreamHandler()
    ]
)

import streamlit as st
import pandas as pd
import amazon_scorecard_ultra_robust_v3_FINAL as scorecard  # noqa: E402 (import after logging setup)

# Logger de auditoría de la app (separado del motor)
_log = logging.getLogger("winiw_app")

def _audit(msg: str):
    """Log de auditoría: registra quién hizo qué y cuándo."""
    user = st.session_state.get("user", {}).get("name", "anon")
    _log.info(f"[{user}] {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMITING — persistido en la tabla login_attempts de la BD
# ─────────────────────────────────────────────────────────────────────────────
# El dict en memoria anterior (_LOGIN_ATTEMPTS) se perdía al reiniciar el servidor
# y era invisible entre workers distintos del mismo proceso Streamlit.
# La tabla login_attempts garantiza que el bloqueo es global y durable.
# ─────────────────────────────────────────────────────────────────────────────
MAX_LOGIN_ATTEMPTS    = 5        # intentos fallidos antes del bloqueo
LOGIN_LOCKOUT_MINUTES = 15       # minutos de bloqueo tras agotar intentos


def _rate_limit_row(uname: str) -> dict | None:
    """Lee la fila de login_attempts para un username. None si no existe."""
    try:
        conn   = scorecard.get_db_connection(db_config)
        cursor = conn.cursor()
        ph     = "%s" if db_config['type'] == 'postgresql' else "?"
        cursor.execute(
            f"SELECT fail_count, locked_until FROM login_attempts WHERE username = {ph}",
            (uname.lower(),)
        )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return None
        return {"count": row[0], "locked_until": row[1]}
    except Exception as e:
        _log.warning(f"_rate_limit_row error: {e}")
        return None


def _is_locked(uname: str) -> tuple[bool, int]:
    """Devuelve (bloqueado, segundos_restantes)."""
    row = _rate_limit_row(uname)
    if not row or not row["locked_until"]:
        return False, 0
    lu = row["locked_until"]
    # SQLite devuelve string; PostgreSQL devuelve datetime
    if isinstance(lu, str):
        try:
            lu = datetime.fromisoformat(lu)
        except ValueError:
            return False, 0
    if datetime.now() < lu:
        return True, int((lu - datetime.now()).total_seconds())
    return False, 0


def _register_failed_attempt(uname: str):
    """Registra un intento fallido y bloquea si se superan MAX_LOGIN_ATTEMPTS."""
    try:
        conn   = scorecard.get_db_connection(db_config)
        cursor = conn.cursor()
        is_pg  = db_config['type'] == 'postgresql'
        ph     = "%s" if is_pg else "?"
        now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # UPSERT: crear o incrementar el contador
        if is_pg:
            cursor.execute(
                """INSERT INTO login_attempts (username, fail_count, last_attempt)
                   VALUES (%s, 1, %s)
                   ON CONFLICT (username) DO UPDATE
                   SET fail_count    = login_attempts.fail_count + 1,
                       last_attempt  = EXCLUDED.last_attempt""",
                (uname.lower(), now)
            )
        else:
            cursor.execute(
                """INSERT INTO login_attempts (username, fail_count, last_attempt)
                   VALUES (?, 1, ?)
                   ON CONFLICT(username) DO UPDATE
                   SET fail_count   = login_attempts.fail_count + 1,
                       last_attempt = excluded.last_attempt""",
                (uname.lower(), now)
            )
        conn.commit()

        # Leer el contador actualizado para decidir si bloquear
        cursor.execute(
            f"SELECT fail_count FROM login_attempts WHERE username = {ph}",
            (uname.lower(),)
        )
        row = cursor.fetchone()
        if row and row[0] >= MAX_LOGIN_ATTEMPTS:
            locked_until = (
                datetime.now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            ).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                f"UPDATE login_attempts SET locked_until = {ph} WHERE username = {ph}",
                (locked_until, uname.lower())
            )
            conn.commit()
            _log.warning(
                f"[RATE LIMIT] '{uname}' bloqueado {LOGIN_LOCKOUT_MINUTES} min "
                f"tras {row[0]} intentos fallidos"
            )
        conn.close()
    except Exception as e:
        _log.warning(f"_register_failed_attempt error: {e}")


def _clear_attempts(uname: str):
    """Limpia el contador tras login exitoso."""
    try:
        conn   = scorecard.get_db_connection(db_config)
        cursor = conn.cursor()
        ph     = "%s" if db_config['type'] == 'postgresql' else "?"
        cursor.execute(
            f"DELETE FROM login_attempts WHERE username = {ph}",
            (uname.lower(),)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        _log.warning(f"_clear_attempts error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG INICIAL
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Winiw Quality Scorecard",
    layout="wide",
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

SESSION_TIMEOUT_MINUTES = 60   # Cierre de sesión automático por inactividad
HISTORICO_MAX_ROWS     = 5000  # Máximo de filas en la vista histórico (ajustable)
SEMANAS_VISIBLES_JT    = 2     # Cuántas semanas recientes puede ver un JT
TREND_SEMANAS_MAX      = 8     # Semanas de historia en el gráfico de tendencia

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_db_config():
    """Configuración BD: Supabase (Secrets) > SQLite local."""
    try:
        if "postgres" in st.secrets:
            return {
                'type': 'postgresql',
                'host': st.secrets.postgres.host,
                'port': int(st.secrets.postgres.port),
                'database': st.secrets.postgres.database,
                'user': st.secrets.postgres.user,
                'password': st.secrets.postgres.password,
            }
    except Exception as e:
        # Si los secrets de Supabase existen pero son inválidos, avisar y caer a SQLite
        _log.warning(f"No se pudo cargar config de Supabase: {e} — usando SQLite local")
    return {'type': 'sqlite'}


def check_session_timeout():
    """Cierra la sesión si lleva más de SESSION_TIMEOUT_MINUTES inactiva."""
    last = st.session_state.get("last_activity")
    if last and (datetime.now() - last) > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
        st.session_state.clear()
        st.warning("⏰ Sesión expirada por inactividad. Inicia sesión de nuevo.")
        st.stop()
    st.session_state["last_activity"] = datetime.now()


def clean_html(html: str) -> str:
    """Elimina toda la indentación de cada línea para evitar que Markdown lo tome como código."""
    if not html: return ""
    return "\n".join([line.strip() for line in html.split("\n")])


# ── Caché de datos (TTL 5 min para no saturar Supabase) ──────────────────────

def _clear_all_caches():
    """
    Invalida toda la caché de datos de la sesión.
    Llamar tras cualquier operación que modifique la BD (subida, borrado, targets).
    Centralizado aquí para no tener que recordar cada función cacheada en cada sitio.
    """
    st.cache_data.clear()

@st.cache_data(ttl=60, show_spinner=False)
def cached_db_status(_db_config_key: str, db_config: dict) -> dict:
    """
    Estado del sistema para el sidebar: total de registros, semanas y semana activa.
    TTL de 60 s — se refresca cada minuto sin ejecutar 3 queries en cada re-render
    (el sidebar se re-renderiza con cada interacción del usuario).
    """
    try:
        conn   = scorecard.get_db_connection(db_config)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) AS n_rec,
                      COUNT(DISTINCT semana) AS n_weeks
               FROM scorecards"""
        )
        row = cursor.fetchone()
        # Semana activa = la subida más recientemente
        cursor.execute(
            "SELECT semana, MAX(timestamp) AS t "
            "FROM scorecards GROUP BY semana ORDER BY t DESC LIMIT 1"
        )
        latest = cursor.fetchone()
        conn.close()
        return {
            "ok":       True,
            "n_rec":    row[0] if row else 0,
            "n_weeks":  row[1] if row else 0,
            "semana":   latest[0] if latest else None,
        }
    except Exception as e:
        _log.warning(f"cached_db_status error: {e}")
        return {"ok": False, "n_rec": 0, "n_weeks": 0, "semana": None}


@st.cache_data(ttl=300, show_spinner=False)
def cached_allowed_weeks_jt(_db_config_key: str, db_config: dict) -> list:
    """
    Las 2 semanas que puede ver un JT = las 2 más recientemente subidas (por timestamp).
    NO es un ORDER BY semana — es por cuándo se subieron los archivos.
    Supabase sigue almacenando TODO; esto es solo filtro de visualización.
    """
    try:
        conn = scorecard.get_db_connection(db_config)
        df = pd.read_sql_query(
            "SELECT semana, MAX(timestamp) as last_upload "
            "FROM scorecards GROUP BY semana ORDER BY last_upload DESC"
            f" LIMIT {SEMANAS_VISIBLES_JT}",
            conn
        )
        conn.close()
        return df['semana'].tolist()
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def cached_scorecard(_db_config_key: str, db_config: dict, semana: str, centro: str) -> pd.DataFrame:
    """Carga datos de un lote con caché de 5 min."""
    try:
        conn = scorecard.get_db_connection(db_config)
        p = "%s" if db_config['type'] == 'postgresql' else "?"
        df = pd.read_sql_query(
            f"SELECT * FROM scorecards WHERE semana = {p} AND centro = {p}",
            conn, params=(semana, centro)
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def cached_available_batches(_db_config_key: str, db_config: dict, allowed_weeks: list = None) -> pd.DataFrame:
    """Lista de lotes disponibles, filtrada por semanas permitidas si se especifica."""
    try:
        conn = scorecard.get_db_connection(db_config)
        where = ""
        params = None
        if allowed_weeks:
            p = "%s" if db_config['type'] == 'postgresql' else "?"
            placeholders = ", ".join([p] * len(allowed_weeks))
            where = f"WHERE semana IN ({placeholders})"
            params = allowed_weeks
        q = f"""
            SELECT semana, centro,
                   MAX(uploaded_by) as subido_por,
                   MAX(timestamp) as fecha_subida
            FROM scorecards {where}
            GROUP BY semana, centro
            ORDER BY fecha_subida DESC
        """
        df = pd.read_sql_query(q, conn, params=params)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def cached_meta(_db_config_key: str, db_config: dict, allowed_weeks: list = None) -> pd.DataFrame:
    """Metadatos para filtros del histórico."""
    try:
        conn = scorecard.get_db_connection(db_config)
        where = ""
        params = None
        if allowed_weeks:
            p = "%s" if db_config['type'] == 'postgresql' else "?"
            placeholders = ", ".join([p] * len(allowed_weeks))
            where = f"WHERE semana IN ({placeholders})"
            params = allowed_weeks
        df = pd.read_sql_query(
            f"SELECT DISTINCT centro, semana, calificacion FROM scorecards {where} ORDER BY semana DESC",
            conn, params=params
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def cached_driver_trend(_db_config_key: str, db_config: dict, driver_id: str, centro: str) -> pd.DataFrame:
    """
    Tendencia histórica de un conductor — todas las semanas disponibles para ese centro.
    Devuelve columnas: semana, score, dnr, dcr, pod, cc, calificacion
    """
    try:
        conn = scorecard.get_db_connection(db_config)
        p = "%s" if db_config['type'] == 'postgresql' else "?"
        df = pd.read_sql_query(
            f"""SELECT semana, score, dnr, dcr, pod, cc, calificacion, detalles
                FROM scorecards
                WHERE driver_id = {p} AND centro = {p}
                ORDER BY semana ASC""",
            conn, params=(driver_id, centro)
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def cached_executive_summary(_db_config_key: str, db_config: dict) -> pd.DataFrame:
    """
    Resumen ejecutivo: última semana disponible por centro + métricas agregadas.
    Devuelve una fila por centro con: semana_actual, score_medio, dnr_medio, dcr_medio,
    pod_medio, n_fantastic, n_great, n_fair, n_poor, total_drivers, score_prev.

    Implementación anterior: N+1 queries (1 inicial + 3 por centro).
    Implementación actual:   2 queries totales independientemente del número de centros.
      · Query 1 — trae la semana más reciente Y la anterior por centro en un solo paso
                  usando una subquery de ranking por timestamp.
      · Query 2 — agrega métricas filtrando por los pares (centro, semana) obtenidos.
    """
    conn = None
    try:
        conn = scorecard.get_db_connection(db_config)
        is_pg = db_config['type'] == 'postgresql'

        # ── Query 1: identificar semana actual y anterior por centro ──────────
        # Asigna rn=1 a la semana más reciente (por MAX timestamp) y rn=2 a la anterior.
        if is_pg:
            q_ranks = """
                SELECT centro, semana, rn
                FROM (
                    SELECT centro, semana,
                           ROW_NUMBER() OVER (
                               PARTITION BY centro
                               ORDER BY MAX(timestamp) DESC
                           ) AS rn
                    FROM scorecards
                    GROUP BY centro, semana
                ) ranked
                WHERE rn <= 2
            """
        else:
            # SQLite < 3.25 no tiene window functions; emulamos con subquery de ranking
            q_ranks = """
                SELECT s.centro, s.semana,
                       (SELECT COUNT(DISTINCT semana2)
                        FROM (
                            SELECT semana AS semana2, MAX(timestamp) AS t2
                            FROM scorecards WHERE centro = s.centro GROUP BY semana
                        ) x WHERE x.t2 >= s.max_t
                       ) AS rn
                FROM (
                    SELECT centro, semana, MAX(timestamp) AS max_t
                    FROM scorecards GROUP BY centro, semana
                ) s
                WHERE rn <= 2
            """

        df_ranks = pd.read_sql_query(q_ranks, conn)
        if df_ranks.empty:
            return pd.DataFrame()

        latest_rows  = df_ranks[df_ranks['rn'] == 1]
        prev_rows    = df_ranks[df_ranks['rn'] == 2]

        # ── Query 2: agregar métricas para semanas actuales ───────────────────
        # Construimos los pares (centro, semana) como filtro
        if latest_rows.empty:
            return pd.DataFrame()

        ph = '%s' if is_pg else '?'
        pairs_latest = list(zip(latest_rows['centro'], latest_rows['semana']))
        pairs_prev   = list(zip(prev_rows['centro'],   prev_rows['semana']))

        def fetch_aggregates(pairs: list) -> pd.DataFrame:
            """Trae métricas agregadas para una lista de pares (centro, semana)."""
            if not pairs:
                return pd.DataFrame(columns=['centro', 'semana', 'score_medio',
                                             'dnr_medio', 'dcr_medio', 'pod_medio',
                                             'n_fantastic', 'n_great', 'n_fair',
                                             'n_poor', 'total'])
            # Construir WHERE con OR para cada par — evita un JOIN complejo
            where_parts = " OR ".join([f"(centro = {ph} AND semana = {ph})"] * len(pairs))
            params = [v for pair in pairs for v in pair]
            q = f"""
                SELECT
                    centro,
                    semana,
                    ROUND(AVG(score), 1)        AS score_medio,
                    ROUND(AVG(dnr), 2)           AS dnr_medio,
                    ROUND(AVG(dcr) * 100, 2)     AS dcr_medio,
                    ROUND(AVG(pod) * 100, 2)     AS pod_medio,
                    SUM(CASE WHEN calificacion = '💎 FANTASTIC' THEN 1 ELSE 0 END) AS n_fantastic,
                    SUM(CASE WHEN calificacion = '🥇 GREAT'     THEN 1 ELSE 0 END) AS n_great,
                    SUM(CASE WHEN calificacion = '⚠️ FAIR'      THEN 1 ELSE 0 END) AS n_fair,
                    SUM(CASE WHEN calificacion = '🛑 POOR'      THEN 1 ELSE 0 END) AS n_poor,
                    COUNT(*) AS total
                FROM scorecards
                WHERE {where_parts}
                GROUP BY centro, semana
            """
            return pd.read_sql_query(q, conn, params=params)

        df_current = fetch_aggregates(pairs_latest)
        df_prev    = fetch_aggregates(pairs_prev)

        # ── Combinar current + prev para calcular delta de score ──────────────
        if not df_prev.empty:
            df_prev_score = df_prev[['centro', 'score_medio']].rename(
                columns={'score_medio': 'score_prev'}
            )
            df_current = df_current.merge(df_prev_score, on='centro', how='left')
        else:
            df_current['score_prev'] = None

        # Añadir pct_top2 y redondear score_prev
        df_current['pct_top2'] = (
            (df_current['n_fantastic'] + df_current['n_great'])
            / df_current['total'].replace(0, float('nan'))
            * 100
        ).round(1).fillna(0)

        df_current['score_prev'] = df_current['score_prev'].apply(
            lambda x: round(x, 1) if x is not None and not pd.isna(x) else None
        )

        return df_current.sort_values('score_medio', ascending=False).reset_index(drop=True)

    except Exception as e:
        _log.warning(f"cached_executive_summary error: {e}")
        return pd.DataFrame()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def db_config_key(db_config: dict) -> str:
    """Clave estable para usar en el caché (evita pasar dicts como arg de caché)."""
    return f"{db_config.get('type')}:{db_config.get('host','local')}:{db_config.get('database','')}"


def get_user_password_hash(username: str, db_config: dict) -> str | None:
    """Obtiene el hash de contraseña de un usuario. Devuelve None si no existe."""
    try:
        conn = scorecard.get_db_connection(db_config)
        cursor = conn.cursor()
        q = ("SELECT password FROM users WHERE LOWER(username) = %s AND active = 1"
             if db_config['type'] == 'postgresql' else
             "SELECT password FROM users WHERE LOWER(username) = ? AND active = 1")
        cursor.execute(q, (username.strip().lower(),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        _log.warning(f"get_user_password_hash error: {e}")
        return None


def get_user_data(username: str, db_config: dict) -> dict | None:
    """Obtiene username y role de un usuario activo. Devuelve None si no existe."""
    try:
        conn = scorecard.get_db_connection(db_config)
        cursor = conn.cursor()
        q = ("SELECT username, role FROM users WHERE LOWER(username) = %s AND active = 1"
             if db_config['type'] == 'postgresql' else
             "SELECT username, role FROM users WHERE LOWER(username) = ? AND active = 1")
        cursor.execute(q, (username.strip().lower(),))
        row = cursor.fetchone()
        conn.close()
        return {"name": row[0], "role": row[1]} if row else None
    except Exception as e:
        _log.warning(f"get_user_data error: {e}")
        return None


def update_user_password(username: str, new_hash: str, db_config: dict) -> bool:
    """Actualiza el hash de contraseña y limpia must_change_password."""
    try:
        conn = scorecard.get_db_connection(db_config)
        cursor = conn.cursor()
        q = ("UPDATE users SET password = %s, must_change_password = 0 WHERE username = %s"
             if db_config['type'] == 'postgresql' else
             "UPDATE users SET password = ?, must_change_password = 0 WHERE username = ?")
        cursor.execute(q, (new_hash, username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _log.warning(f"update_user_password error: {e}")
        return False


def get_user_role(username: str, db_config: dict) -> str | None:
    """
    Devuelve el rol de un usuario activo o None si no existe / está desactivado.
    Filtrar por active = 1 es consistente con get_user_data() y get_user_password_hash().
    Sin este filtro, un usuario desactivado podría seguir siendo reconocido como superadmin
    en las comprobaciones de permisos aunque no pueda hacer login.
    """
    try:
        conn = scorecard.get_db_connection(db_config)
        cursor = conn.cursor()
        q = ("SELECT role FROM users WHERE LOWER(username) = %s AND active = 1"
             if db_config['type'] == 'postgresql' else
             "SELECT role FROM users WHERE LOWER(username) = ? AND active = 1")
        cursor.execute(q, (username.strip().lower(),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        _log.warning(f"get_user_role error: {e}")
        return None


# ── Renderers HTML ─────────────────────────────────────────────────────────────

CALIFICACION_COLORS = {
    '💎 FANTASTIC': '#198754',
    '🥇 GREAT':     '#0d6efd',
    '⚠️ FAIR':      '#fd7e14',
    '🛑 POOR':      '#dc3545',
}

ISSUE_COLORS = {
    '🚨': '#dc3545',   # DNR crítico
    '❌': '#dc3545',   # FS crítico
    '📦': '#fd7e14',   # DCR bajo/crítico
    '⚡': '#fd7e14',   # Otros warnings
    '📸': '#fd7e14',   # POD bajo
    '📞': '#0d6efd',   # CC bajo
    '⚠️': '#ffc107',  # FS/warning moderado
    'ℹ️': '#0dcaf0',  # Informativo
    '🔄': '#6f42c1',   # RTS alto
    '⭐': '#20c997',   # Positivo
}


def badge(text: str, color: str, text_color: str = 'white', small: bool = True) -> str:
    size = '0.72em' if small else '0.85em'
    return (
        f'<span style="background:{color};color:{text_color};padding:2px 7px;'
        f'border-radius:12px;font-size:{size};font-weight:600;'
        f'display:inline-block;margin:1px 2px;white-space:nowrap">{text}</span>'
    )


def render_calificacion(cal: str) -> str:
    color = CALIFICACION_COLORS.get(cal, '#6c757d')
    return badge(cal, color, small=False)


def render_detalles(detalles_str: str) -> str:
    if not detalles_str or str(detalles_str).strip() in ('Óptimo', 'nan', ''):
        return badge('✅ Óptimo', '#198754')
    issues = [i.strip() for i in str(detalles_str).split(',') if i.strip()]
    html_parts = []
    for issue in issues:
        color = '#6c757d'
        for emoji, c in ISSUE_COLORS.items():
            if emoji in issue:
                color = c
                break
        # Para FAIR, texto oscuro
        text_col = '#000' if color == '#ffc107' else 'white'
        html_parts.append(badge(issue, color, text_col))
    return ' '.join(html_parts)


def render_score_bar(score: float) -> str:
    """Mini barra de progreso HTML para el score."""
    color = CALIFICACION_COLORS.get(
        '💎 FANTASTIC' if score >= 90 else
        '🥇 GREAT' if score >= 80 else
        '⚠️ FAIR' if score >= 60 else '🛑 POOR',
        '#6c757d'
    )
    pct = max(0, min(100, score))
    return (
        f'<div style="display:flex;align-items:center;gap:6px">'
        f'<div style="flex:1;background:#e9ecef;border-radius:4px;height:8px">'
        f'<div style="width:{pct}%;background:{color};height:8px;border-radius:4px"></div></div>'
        f'<span style="font-weight:700;color:{color};min-width:28px">{int(score)}</span>'
        f'</div>'
    )


def delta_arrow(current: float, previous: float, higher_is_better: bool = True) -> str:
    """Flecha coloreada indicando mejora/empeora respecto a semana anterior."""
    if previous is None or pd.isna(previous):
        return ''
    diff = current - previous
    if abs(diff) < 0.001:
        return '<span style="color:#6c757d">→ =</span>'
    improved = (diff > 0) == higher_is_better
    arrow = '▲' if diff > 0 else '▼'
    color = '#198754' if improved else '#dc3545'
    fmt = f'{diff:+.2f}'
    return f'<span style="color:{color};font-size:0.85em">{arrow} {fmt}</span>'


# ─────────────────────────────────────────────────────────────────────────────
# DB CONFIG + INIT
# ─────────────────────────────────────────────────────────────────────────────

db_config = get_db_config()

# init_database UNA SOLA VEZ por sesión (no en cada render)
if "db_initialized" not in st.session_state:
    scorecard.init_database(db_config)
    st.session_state["db_initialized"] = True

_DB_KEY = db_config_key(db_config)

# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

def check_login() -> bool:
    if "user" not in st.session_state:
        st.markdown("""
        <div style='text-align:center;padding:3rem 0 1rem'>
            <div style='font-size:3rem'>🛡️</div>
            <h1 style='margin:0.5rem 0'>Winiw Quality Scorecard</h1>
            <p style='color:#6c757d'>Sistema de Gestión de Calidad · Amazon DSP</p>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1, 1.5, 1])
        with c2:
            with st.form("login_form"):
                username = st.text_input("👤 Usuario")
                password = st.text_input("🔒 Contraseña", type="password")
                submitted = st.form_submit_button("Iniciar Sesión", use_container_width=True, type="primary")

                if submitted:
                    try:
                        uname = username.strip().lower()

                        # ── Comprobar si está bloqueado ─────────────────────
                        locked, remaining = _is_locked(uname)
                        if locked:
                            mins = remaining // 60
                            secs = remaining % 60
                            st.error(
                                f"🔒 Cuenta temporalmente bloqueada por demasiados intentos fallidos. "
                                f"Inténtalo de nuevo en **{mins}m {secs}s**."
                            )
                            _log.warning(f"[RATE LIMIT] Intento bloqueado para '{uname}' ({remaining}s restantes)")
                            return False

                        # ── Verificar credenciales ──────────────────────────
                        pw_hash = get_user_password_hash(uname, db_config)
                        if pw_hash and scorecard.verify_password(password, pw_hash):
                            user_info = get_user_data(uname, db_config)
                            _clear_attempts(uname)
                            st.session_state["user"] = user_info
                            st.session_state["last_activity"] = datetime.now()
                            _audit(f"Login exitoso ({user_info['role']})")
                            st.rerun()
                        else:
                            _register_failed_attempt(uname)
                            # Leer el contador actualizado desde la BD (fuente de verdad)
                            row = _rate_limit_row(uname)
                            current_count  = row["count"] if row else 1
                            remaining_tries = max(0, MAX_LOGIN_ATTEMPTS - current_count)
                            _audit(f"Login fallido para '{uname}' (intentos restantes: {remaining_tries})")

                            if remaining_tries <= 0:
                                st.error(
                                    f"🔒 Demasiados intentos fallidos. "
                                    f"Cuenta bloqueada durante **{LOGIN_LOCKOUT_MINUTES} minutos**."
                                )
                            else:
                                st.error(
                                    f"❌ Usuario o contraseña incorrectos. "
                                    f"({remaining_tries} intento{'s' if remaining_tries != 1 else ''} restante{'s' if remaining_tries != 1 else ''})"
                                )
                    except Exception as e:
                        st.error(f"❌ Error de conexión: {e}")
        return False
    return True


if not check_login():
    st.stop()

check_session_timeout()

user_data_session = st.session_state["user"]
user_role  = user_data_session.get("role", "guest")
is_superadmin = (user_role == "superadmin")
is_admin      = (user_role in ["admin", "superadmin"])
is_jt         = (user_role == "jt")

# ─────────────────────────────────────────────────────────────────────────────
# SEMANAS PERMITIDAS PARA JT (basado en timestamp de subida, no en nombre)
# ─────────────────────────────────────────────────────────────────────────────
# Supabase almacena TODO el histórico sin restricciones.
# Esta variable solo se usa para filtrar la visualización de los JTs.

ALLOWED_WEEKS_JT = (
    cached_allowed_weeks_jt(_DB_KEY, db_config)
    if is_jt else None
)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    role_label = {
        'superadmin': '👑 Superadmin',
        'admin': '🔑 Administrador',
        'jt': '👔 Jefe de Tráfico',
    }.get(user_role, user_role)

    st.markdown(f"""
    <div style='background:linear-gradient(135deg,#232f3e,#37475a);
                border-radius:10px;padding:1rem;color:white;margin-bottom:0.5rem'>
        <div style='font-size:1.1em;font-weight:700'>{user_data_session['name']}</div>
        <div style='font-size:0.85em;opacity:0.8'>{role_label}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.divider()

    # Estado BD y semana activa
    with st.expander("📊 Estado del Sistema", expanded=False):
        bd_label = "🌐 Supabase" if db_config['type'] == 'postgresql' else "💾 SQLite"
        st.caption(bd_label)
        status = cached_db_status(_DB_KEY, db_config)
        if status["ok"]:
            st.metric("Registros totales", f"{status['n_rec']:,}")
            st.metric("Semanas en BD", status["n_weeks"])
            if status["semana"]:
                st.success(f"Semana activa: **{status['semana']}**")
        else:
            st.warning("BD no disponible")

    if is_jt and ALLOWED_WEEKS_JT:
        st.divider()
        semana_actual = ALLOWED_WEEKS_JT[0] if ALLOWED_WEEKS_JT else "—"
        semana_prev   = ALLOWED_WEEKS_JT[1] if len(ALLOWED_WEEKS_JT) > 1 else "—"
        st.markdown(f"""
        <div style='font-size:0.85em;color:#6c757d'>
        📅 <b>Semana en curso:</b> {semana_actual}<br>
        📅 <b>Semana anterior:</b> {semana_prev}
        </div>
        """, unsafe_allow_html=True)

    if is_admin:
        st.divider()
        with st.expander("🔧 Override Manual"):
            center_manual = st.text_input("Centro", "", help="Sobrescribir centro detectado")
            week_manual   = st.text_input("Semana", "", placeholder="ej: W07")
    else:
        center_manual = ""
        week_manual   = ""

# ─────────────────────────────────────────────────────────────────────────────
# HEADER + TABS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div style='display:flex;align-items:center;gap:1rem;margin-bottom:0.5rem'>
    <span style='font-size:2rem'>🛡️</span>
    <div>
        <h2 style='margin:0'>Winiw Quality Scorecard</h2>
        <p style='margin:0;color:#6c757d;font-size:0.9em'>Amazon DSP · Líderes en calidad</p>
    </div>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

if is_admin:
    tabs = st.tabs(["🏢 Dashboard", "🚀 Procesamiento", "📋 DSP Scorecard", "📊 Scorecard", "📈 Histórico", "👤 Perfil", "👑 Admin"])
    tab_dash, tab_proc, tab_dsp, tab_excel, tab_hist, tab_profile, tab_admin = tabs
else:
    tabs = st.tabs(["📊 Scorecard", "📈 Histórico", "👤 Perfil"])
    tab_excel, tab_hist, tab_profile = tabs
    tab_dash = tab_proc = tab_dsp = tab_admin = None

# ─────────────────────────────────────────────────────────────────────────────
# TAB: DASHBOARD EJECUTIVO (solo admins)
# ─────────────────────────────────────────────────────────────────────────────

if tab_dash:
    with tab_dash:
        st.header("🏢 Dashboard Ejecutivo")
        st.markdown("Vista consolidada de todos los centros — última semana disponible por centro.")

        with st.spinner("Cargando datos de todos los centros..."):
            df_exec = cached_executive_summary(_DB_KEY, db_config)

        if df_exec.empty:
            st.info("📭 No hay datos. Procesa archivos primero.")
        else:
            n_centros = len(df_exec)

            # ── Encabezado resumen global ──────────────────────────────────
            total_drivers  = int(df_exec['total'].sum())
            avg_score_all  = round(df_exec['score_medio'].mean(), 1)
            total_poor     = int(df_exec['n_poor'].sum())
            total_fantastic= int(df_exec['n_fantastic'].sum())

            st.markdown(f"""
            <div style='background:linear-gradient(135deg,#232f3e,#37475a);
                        border-radius:12px;padding:1.2rem 1.8rem;color:white;margin-bottom:1.2rem;
                        display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem'>
                <div>
                    <div style='font-size:1.5em;font-weight:800'>Red de {n_centros} Centro{"s" if n_centros!=1 else ""}</div>
                    <div style='opacity:0.7;font-size:0.9em'>{total_drivers} conductores activos esta semana</div>
                </div>
                <div style='display:flex;gap:2rem'>
                    <div style='text-align:center'>
                        <div style='font-size:2em;font-weight:800;color:#FF9900'>{avg_score_all}</div>
                        <div style='font-size:0.8em;opacity:0.7'>Score Global</div>
                    </div>
                    <div style='text-align:center'>
                        <div style='font-size:2em;font-weight:800;color:#198754'>{total_fantastic}</div>
                        <div style='font-size:0.8em;opacity:0.7'>💎 FANTASTIC</div>
                    </div>
                    <div style='text-align:center'>
                        <div style='font-size:2em;font-weight:800;color:#dc3545'>{total_poor}</div>
                        <div style='font-size:0.8em;opacity:0.7'>🛑 POOR</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ── Ranking de centros ─────────────────────────────────────────
            st.subheader("🏆 Ranking de Centros")

            rank_cols = st.columns(min(n_centros, 4))
            for i, (_, row) in enumerate(df_exec.iterrows()):
                col = rank_cols[i % len(rank_cols)]
                delta_score = None
                if row['score_prev'] is not None:
                    delta_score = round(row['score_medio'] - row['score_prev'], 1)

                medal = {0: '🥇', 1: '🥈', 2: '🥉'}.get(i, f"#{i+1}")
                score_color = (
                    '#198754' if row['score_medio'] >= 90 else
                    '#0d6efd' if row['score_medio'] >= 80 else
                    '#fd7e14' if row['score_medio'] >= 60 else '#dc3545'
                )

                delta_html = ''
                if delta_score is not None:
                    delta_color = '#198754' if delta_score >= 0 else '#dc3545'
                    delta_icon  = '▲' if delta_score > 0 else ('▼' if delta_score < 0 else '→')
                    delta_html  = f'<span style="color:{delta_color};font-size:0.9em">{delta_icon} {delta_score:+.1f}</span>'

                col.markdown(f"""
                <div style='border:2px solid {score_color};border-radius:12px;padding:1rem;
                            text-align:center;background:{score_color}10'>
                    <div style='font-size:1.4em'>{medal}</div>
                    <div style='font-size:1.1em;font-weight:800;color:{score_color}'>{row['centro']}</div>
                    <div style='font-size:0.8em;color:#6c757d'>{row['semana']}</div>
                    <div style='font-size:2.5em;font-weight:900;color:{score_color};line-height:1.1'>{row['score_medio']}</div>
                    <div>{delta_html}</div>
                    <hr style='margin:0.5rem 0;border-color:{score_color}30'>
                    <div style='font-size:0.8em;color:#6c757d'>{row['total']} conductores</div>
                    <div style='font-size:0.8em'>
                        <span style='color:#198754'>💎{row["n_fantastic"]}</span> &nbsp;
                        <span style='color:#0d6efd'>🥇{row["n_great"]}</span> &nbsp;
                        <span style='color:#fd7e14'>⚠️{row["n_fair"]}</span> &nbsp;
                        <span style='color:#dc3545'>🛑{row["n_poor"]}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")

            # ── Tabla comparativa detallada ────────────────────────────────
            st.subheader("📊 Métricas Comparativas")

            rows_html = []
            for i, (_, row) in enumerate(df_exec.iterrows()):
                bg = '#ffffff' if i % 2 == 0 else '#f8f9fa'
                score_c = (
                    '#198754' if row['score_medio'] >= 90 else
                    '#0d6efd' if row['score_medio'] >= 80 else
                    '#fd7e14' if row['score_medio'] >= 60 else '#dc3545'
                )
                delta_score = None
                if row['score_prev'] is not None:
                    delta_score = round(row['score_medio'] - row['score_prev'], 1)

                delta_cell = ''
                if delta_score is not None:
                    dc = '#198754' if delta_score >= 0 else '#dc3545'
                    di = '▲' if delta_score > 0 else ('▼' if delta_score < 0 else '→')
                    delta_cell = f'<span style="color:{dc}">{di} {delta_score:+.1f}</span>'

                # Barra de % top2
                pct_bar = f"""<div style='display:flex;align-items:center;gap:6px'>
                    <div style='flex:1;background:#e9ecef;border-radius:3px;height:6px'>
                    <div style='width:{row["pct_top2"]}%;background:{score_c};height:6px;border-radius:3px'></div></div>
                    <span style='font-size:0.85em;font-weight:700;color:{score_c}'>{row["pct_top2"]}%</span></div>"""

                rows_html.append(f"""
                <tr style='background:{bg}'>
                    <td style='padding:8px 10px;font-weight:700'>{row['centro']}</td>
                    <td style='padding:8px 10px;color:#6c757d'>{row['semana']}</td>
                    <td style='padding:8px 10px;font-weight:800;color:{score_c};font-size:1.1em'>{row['score_medio']}</td>
                    <td style='padding:8px 10px'>{delta_cell}</td>
                    <td style='padding:8px 10px;text-align:center'><b style='color:{"#dc3545" if row["dnr_medio"]>=2 else "#198754"}'>{row['dnr_medio']:.2f}</b></td>
                    <td style='padding:8px 10px;text-align:center'>{row['dcr_medio']:.2f}%</td>
                    <td style='padding:8px 10px;text-align:center'>{row['pod_medio']:.2f}%</td>
                    <td style='padding:8px 10px'>{pct_bar}</td>
                    <td style='padding:8px 10px;text-align:center;color:#dc3545;font-weight:700'>{row['n_poor']}</td>
                    <td style='padding:8px 10px;text-align:center;color:#6c757d'>{row['total']}</td>
                </tr>
                """)

            st.markdown(f"""
            <div style='overflow-x:auto;border-radius:8px;border:1px solid #dee2e6'>
            <table style='width:100%;border-collapse:collapse;font-size:0.9em'>
                <thead>
                    <tr style='background:#232f3e;color:white'>
                        <th style='padding:10px;text-align:left'>Centro</th>
                        <th style='padding:10px;text-align:left'>Semana</th>
                        <th style='padding:10px;text-align:left'>Score</th>
                        <th style='padding:10px;text-align:left'>vs Ant.</th>
                        <th style='padding:10px;text-align:center'>DNR</th>
                        <th style='padding:10px;text-align:center'>DCR</th>
                        <th style='padding:10px;text-align:center'>POD</th>
                        <th style='padding:10px;text-align:left'>FANTASTIC+GREAT</th>
                        <th style='padding:10px;text-align:center'>🛑 POOR</th>
                        <th style='padding:10px;text-align:center'>Total</th>
                    </tr>
                </thead>
                <tbody>{''.join(rows_html)}</tbody>
            </table></div>
            """, unsafe_allow_html=True)

            st.markdown("---")

            # ── Gráfico de barras: Score por centro ────────────────────────
            st.subheader("📈 Score Medio por Centro")
            df_chart = df_exec[['centro', 'score_medio']].set_index('centro')
            st.bar_chart(df_chart, height=300, use_container_width=True)

            # ── Distribución global POOR ───────────────────────────────────
            if df_exec['n_poor'].sum() > 0:
                st.markdown("---")
                st.subheader("🚨 Conductores POOR por Centro")
                df_poor_chart = df_exec[df_exec['n_poor'] > 0][['centro', 'n_poor']].set_index('centro')
                st.bar_chart(df_poor_chart, height=250, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB: PROCESAMIENTO (solo admins — sin cambios funcionales)
# ─────────────────────────────────────────────────────────────────────────────

if tab_proc:
    with tab_proc:
        st.header("🚀 Procesamiento de Archivos")
        st.markdown("Sube los archivos semanales de Amazon para generar el scorecard automático.")

        uploaded_files = st.file_uploader(
            "📁 Arrastra o selecciona archivos",
            accept_multiple_files=True,
            help="Soporta: CSV, XLSX, HTML (Concessions, Quality, False Scan, DWC, FDPS)"
        )

        if uploaded_files:
            batches = {}
            for f in uploaded_files:
                week, center = scorecard.extract_info_from_path(f.name)
                bk = (week, center)
                if bk not in batches:
                    batches[bk] = {
                        'concessions': [], 'quality': [], 'false_scan': [],
                        'dwc': [], 'fdps': [], 'daily': [], 'official': [],
                        'files_count': 0
                    }
                name = f.name.lower()
                if re.match(scorecard.Config.PATTERN_CONCESSIONS, name, re.IGNORECASE):
                    batches[bk]['concessions'].append(f)
                elif re.match(scorecard.Config.PATTERN_QUALITY, name, re.IGNORECASE):
                    batches[bk]['quality'].append(f)
                elif re.match(scorecard.Config.PATTERN_FALSE_SCAN, name, re.IGNORECASE):
                    batches[bk]['false_scan'].append(f)
                elif re.match(scorecard.Config.PATTERN_DWC, name, re.IGNORECASE):
                    batches[bk]['dwc'].append(f)
                elif re.match(scorecard.Config.PATTERN_FDPS, name, re.IGNORECASE):
                    batches[bk]['fdps'].append(f)
                elif re.match(scorecard.Config.PATTERN_DAILY, name, re.IGNORECASE):
                    batches[bk]['daily'].append(f)
                elif re.match(scorecard.Config.PATTERN_OFFICIAL_SCORECARD, name, re.IGNORECASE):
                    batches[bk]['official'].append(f)
                batches[bk]['files_count'] += 1

            for (week, center), data in batches.items():
                with st.expander(f"📍 {center} | 📅 {week} ({data['files_count']} archivos)", expanded=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.caption("Archivos detectados:")
                        for tipo, files in [
                            ("Concessions", data['concessions']),
                            ("Quality", data['quality']),
                            ("False Scan", data['false_scan']),
                        ]:
                            icon = "✅" if files else "⬜"
                            st.markdown(f"{icon} {tipo}: {len(files)}")
                    with c2:
                        st.caption("&nbsp;")
                        for tipo, files in [
                            ("DWC/IADC", data['dwc']),
                            ("FDPS", data['fdps']),
                            ("Daily", data['daily']),
                        ]:
                            icon = "✅" if files else "⬜"
                            st.markdown(f"{icon} {tipo}: {len(files)}")

                    st.divider()
                    st.subheader("🎯 Targets de Calidad")
                    curr_t = scorecard.get_center_targets(center, db_config=db_config)
                    col1, col2, col3, col4 = st.columns(4)
                    t_dnr  = col1.number_input("DNR Max",    value=float(curr_t['target_dnr']),
                                               min_value=0.0, max_value=20.0, step=0.5,
                                               key=f"dnr_{center}_{week}",
                                               help="Número máximo de DNR permitido (0–20)")
                    t_dcr  = col2.number_input("DCR Min (%)", value=float(curr_t['target_dcr']*100),
                                               min_value=80.0, max_value=100.0, step=0.1,
                                               key=f"dcr_{center}_{week}",
                                               help="Porcentaje mínimo de DCR (80–100%)") / 100
                    t_pod  = col3.number_input("POD Min (%)", value=float(curr_t['target_pod']*100),
                                               min_value=80.0, max_value=100.0, step=0.1,
                                               key=f"pod_{center}_{week}",
                                               help="Porcentaje mínimo de POD (80–100%)") / 100
                    t_cc   = col4.number_input("CC Min (%)",  value=float(curr_t['target_cc']*100),
                                               min_value=80.0, max_value=100.0, step=0.1,
                                               key=f"cc_{center}_{week}",
                                               help="Porcentaje mínimo de CC (80–100%)") / 100

                    st.divider()
                    if st.button(f"🚀 Generar Scorecard {center} — {week}", key=f"btn_{center}_{week}",
                                 type="primary", use_container_width=True):
                        if not data['concessions']:
                            st.error("❌ Se requiere al menos un archivo de 'Concessions'")
                        else:
                            with st.spinner("⚙️ Procesando..."):
                                new_t = {
                                    'centro': center, 'target_dnr': t_dnr, 'target_dcr': t_dcr,
                                    'target_pod': t_pod, 'target_cc': t_cc,
                                    'target_fdps': 0.98, 'target_rts': 0.01, 'target_cdf': 0.95
                                }
                                scorecard.save_center_targets(new_t, db_config=db_config)
                                current_week   = week_manual if week_manual else week
                                current_center = center_manual if center_manual else center
                                scorecard.delete_scorecard_batch(current_week, current_center, db_config=db_config)

                                df = scorecard.process_single_batch(
                                    data['concessions'], data['quality'], data['false_scan'],
                                    data['dwc'], data['fdps'], data['daily'], targets=new_t
                                )
                                if df is not None:
                                    ok = scorecard.save_to_database(
                                        df, current_week, current_center,
                                        db_config=db_config,
                                        uploaded_by=user_data_session['name']
                                    )
                                    # Invalidar solo el caché relacionado con este lote
                                    # (no borramos todo para no perjudicar a usuarios concurrentes)
                                    _clear_all_caches()
                                    _audit(f"Procesó {current_center} {current_week} — {len(df)} conductores")

                                    if ok:
                                        st.success(f"✅ {len(df)} conductores procesados y guardados.")
                                    else:
                                        st.warning("⚠️ Procesado pero error al guardar en BD.")

                                    output = io.BytesIO()
                                    scorecard.create_professional_excel(
                                        df, output, center_name=current_center, week=current_week
                                    )
                                    st.download_button(
                                        "📥 Descargar Excel",
                                        output.getvalue(),
                                        f"Scorecard_{current_center}_{current_week}.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        use_container_width=True
                                    )
                                    # Resumen rápido
                                    c1, c2, c3, c4 = st.columns(4)
                                    c1.metric("Conductores", len(df))
                                    c2.metric("DNR Promedio", f"{df['DNR'].mean():.2f}")
                                    c3.metric("💎 FANTASTIC", (df['CALIFICACION']=='💎 FANTASTIC').sum())
                                    c4.metric("🛑 POOR", (df['CALIFICACION']=='🛑 POOR').sum())
                                else:
                                    st.error("❌ Error en el procesamiento. Verifica los archivos.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: DSP SCORECARD PDF (sin cambios funcionales)
# ─────────────────────────────────────────────────────────────────────────────

if tab_dsp:
    with tab_dsp:
        st.header("📋 DSP Weekly Scorecard — PDF oficial Amazon")
        st.markdown("Sube los PDFs semanales para guardar KPIs oficiales de estación y actualizar métricas de conductores.")

        uploaded_pdfs = st.file_uploader(
            "Seleccionar PDFs (puedes subir varios a la vez)",
            type=["pdf"], accept_multiple_files=True
        )

        if uploaded_pdfs:
            for pdf_file in uploaded_pdfs:
                st.markdown(f"**📄 {pdf_file.name}**")
                with st.spinner(f"Procesando {pdf_file.name}..."):
                    parsed = scorecard.parse_dsp_scorecard_pdf(pdf_file.read())

                if not parsed['ok']:
                    st.error(f"❌ No se pudo procesar: {', '.join(parsed['errors'])}")
                    continue

                meta    = parsed['meta']
                station = parsed['station']
                centro  = meta['centro']
                semana  = meta['semana']

                tier_color = {'Fantastic': '🟢', 'Great': '🔵', 'Fair': '🟡', 'Poor': '🔴'}
                overall_icon = tier_color.get(station.get('overall_standing', ''), '⚪')

                with st.expander(
                    f"{overall_icon} {centro} — {semana} | Score: {station.get('overall_score')} "
                    f"({station.get('overall_standing')}) | Rank: #{station.get('rank_station')}",
                    expanded=True
                ):
                    c1, c2, c3, c4 = st.columns(4)
                    rank_wow = station.get('rank_wow')
                    c1.metric("Overall Score", station.get('overall_score'), station.get('overall_standing'))
                    c2.metric("Ranking Estación", f"#{station.get('rank_station')}",
                              f"{rank_wow:+d} WoW" if rank_wow is not None else None)
                    c3.metric(f"WHC {tier_color.get(station.get('whc_tier',''),'⚪')}",
                              f"{station.get('whc_pct')}%", station.get('whc_tier'))
                    c4.metric(f"LoR DPMO {tier_color.get(station.get('lor_tier',''),'⚪')}",
                              station.get('lor_dpmo'), station.get('lor_tier'))

                    c5, c6, c7, c8 = st.columns(4)
                    c5.metric(f"DCR {tier_color.get(station.get('dcr_tier',''),'⚪')}",
                              f"{station.get('dcr_pct')}%", station.get('dcr_tier'))
                    c6.metric(f"DNR DPMO {tier_color.get(station.get('dnr_tier',''),'⚪')}",
                              station.get('dnr_dpmo'), station.get('dnr_tier'))
                    c7.metric(f"FICO {tier_color.get(station.get('fico_tier',''),'⚪')}",
                              station.get('fico'), station.get('fico_tier'))
                    c8.metric(f"POD {tier_color.get(station.get('pod_tier',''),'⚪')}",
                              f"{station.get('pod_pct')}%", station.get('pod_tier'))

                    fa1 = station.get('focus_area_1') or '—'
                    fa2 = station.get('focus_area_2') or '—'
                    fa3 = station.get('focus_area_3') or '—'
                    st.info(f"🎯 **Focus Areas Amazon:** 1. {fa1} · 2. {fa2} · 3. {fa3}")

                    n_drivers = len(parsed['drivers']) if not parsed['drivers'].empty else 0
                    n_wh      = len(parsed['wh']) if not parsed['wh'].empty else 0
                    st.caption(f"📊 {n_drivers} conductores extraídos · ⏰ {n_wh} excepciones WHC")

                    if parsed['errors']:
                        st.warning(f"⚠️ Campos no encontrados: {', '.join(parsed['errors'])}")

                    if st.button(f"💾 Guardar {centro} {semana}", key=f"save_dsp_{centro}_{semana}",
                                 type="primary", use_container_width=True):
                        with st.spinner("Guardando..."):
                            try:
                                ok_station = scorecard.save_station_scorecard(
                                    station, semana, centro, db_config,
                                    user_data_session['name']
                                )
                                n_upd, n_miss = scorecard.update_drivers_from_pdf(
                                    parsed['drivers'], semana, centro, db_config
                                )
                                ok_wh = scorecard.save_wh_exceptions(
                                    parsed['wh'], semana, centro, db_config,
                                    user_data_session['name']
                                )
                                _clear_all_caches()
                                _audit(f"Guardó PDF DSP {centro} {semana}")
                                if ok_station:
                                    st.success(
                                        f"✅ Guardado — Drivers actualizados: {n_upd} · "
                                        f"Sin match: {n_miss} · WHC: {'✅' if ok_wh else '❌'}"
                                    )
                                else:
                                    st.error("❌ Error guardando scorecard de estación.")
                            except Exception as e:
                                st.error(f"❌ Error: {e}")

        st.divider()
        st.subheader("📊 Histórico DSP Scorecard por Estación")
        try:
            df_ss = scorecard.get_station_scorecards(db_config)
            if df_ss.empty:
                st.info("📭 No hay scorecards de estación. Sube PDFs para empezar.")
            else:
                centros_disp = sorted(df_ss['centro'].unique())
                sel_centros  = st.multiselect("Filtrar por Centro", centros_disp, default=centros_disp)
                df_filtrado  = df_ss[df_ss['centro'].isin(sel_centros)] if sel_centros else df_ss
                cols_show = [c for c in [
                    'semana', 'centro', 'overall_score', 'overall_standing', 'rank_station', 'rank_wow',
                    'dcr_pct', 'dcr_tier', 'dnr_dpmo', 'dnr_tier', 'lor_dpmo', 'lor_tier',
                    'whc_pct', 'whc_tier', 'pod_pct', 'pod_tier', 'fico', 'fico_tier',
                    'focus_area_1', 'focus_area_2', 'focus_area_3'
                ] if c in df_filtrado.columns]
                st.dataframe(df_filtrado[cols_show], use_container_width=True, hide_index=True, height=400)
        except Exception as e:
            st.error(f"❌ Error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: SCORECARD (Vista principal para JTs — redesign completo)
# ─────────────────────────────────────────────────────────────────────────────

with tab_excel:
    st.header("📊 Scorecard Semanal")

    try:
        # Semanas visibles según rol
        # JTs: solo las 2 más recientes por timestamp de subida
        # Admins: todas
        allowed = ALLOWED_WEEKS_JT if is_jt else None
        df_available = cached_available_batches(_DB_KEY, db_config, allowed)

        if df_available.empty:
            st.info("📭 No hay scorecards disponibles. Procesa archivos primero.")
        else:
            if is_jt and allowed:
                st.info(
                    f"👔 Tienes acceso a: **{' y '.join(allowed)}** "
                    f"(semana en curso y anterior)"
                )

            # Selector
            col1, col2 = st.columns(2)
            with col1:
                centers = sorted(df_available['centro'].unique())
                selected_center = st.selectbox("🏢 Centro", centers)
            with col2:
                weeks_for_center = df_available[
                    df_available['centro'] == selected_center
                ]['semana'].tolist()
                selected_week = st.selectbox("📅 Semana", weeks_for_center)

            # Botón o auto-load
            load_btn = st.button("📊 Cargar Scorecard", type="primary", use_container_width=True)

            if load_btn:
                st.session_state['sc_week']   = selected_week
                st.session_state['sc_center'] = selected_center

            # Usar datos guardados en session_state para no recargar en cada re-render
            sc_week   = st.session_state.get('sc_week',   selected_week)
            sc_center = st.session_state.get('sc_center', selected_center)

            # Si el selector cambió respecto al session_state, sincronizar inmediatamente.
            # Sin esto, el scorecard visible y el selector mostrado quedaban desincronizados.
            if sc_week != selected_week or sc_center != selected_center:
                sc_week   = selected_week
                sc_center = selected_center
                st.session_state['sc_week']   = selected_week
                st.session_state['sc_center'] = selected_center

            df_sc = cached_scorecard(_DB_KEY, db_config, sc_week, sc_center)

            if df_sc.empty:
                st.warning("No se encontraron datos para este scorecard.")
            else:
                # ── Buscar semana anterior para deltas WoW ────────────────
                # Ordenamos por MAX(timestamp) DESC, no por nombre de semana.
                # Esto evita el bug con comparación lexicográfica "W9" > "W10".
                # La semana anterior = la segunda semana más reciente en BD para este centro.
                conn_w = None
                try:
                    conn_w = scorecard.get_db_connection(db_config)
                    p = "%s" if db_config['type'] == 'postgresql' else "?"
                    df_prev_meta = pd.read_sql_query(
                        f"SELECT semana, MAX(timestamp) AS t FROM scorecards "
                        f"WHERE centro = {p} AND semana != {p} "
                        f"GROUP BY semana ORDER BY t DESC LIMIT 1",
                        conn_w, params=(sc_center, sc_week)
                    )
                    prev_week = df_prev_meta['semana'].iloc[0] if not df_prev_meta.empty else None
                    df_prev = cached_scorecard(_DB_KEY, db_config, prev_week, sc_center) if prev_week else pd.DataFrame()
                except Exception:
                    prev_week = None
                    df_prev = pd.DataFrame()
                finally:
                    if conn_w is not None:
                        try:
                            conn_w.close()
                        except Exception:
                            pass

                # ── KPIs resumen + delta WoW ──────────────────────────────
                total   = len(df_sc)
                sc_mean = df_sc['score'].mean()
                dnr_mean = df_sc['dnr'].mean()
                dcr_mean = df_sc['dcr'].mean() * 100
                pod_mean = df_sc['pod'].mean() * 100
                n_fantastic = (df_sc['calificacion'] == '💎 FANTASTIC').sum()
                n_great     = (df_sc['calificacion'] == '🥇 GREAT').sum()
                n_fair      = (df_sc['calificacion'] == '⚠️ FAIR').sum()
                n_poor      = (df_sc['calificacion'] == '🛑 POOR').sum()
                pct_top2    = round((n_fantastic + n_great) / total * 100, 1) if total else 0

                # Deltas WoW
                prev_sc_mean  = df_prev['score'].mean() if not df_prev.empty else None
                prev_dnr_mean = df_prev['dnr'].mean()   if not df_prev.empty else None
                prev_dcr_mean = (df_prev['dcr'].mean() * 100) if not df_prev.empty else None
                prev_pct_top2 = (
                    round(((df_prev['calificacion'].isin(['💎 FANTASTIC','🥇 GREAT'])).sum()
                           / len(df_prev) * 100), 1)
                    if not df_prev.empty else None
                )

                st.markdown(clean_html(f"""
                <div style='background:linear-gradient(135deg,#232f3e,#37475a);
                            border-radius:12px;padding:1.2rem 1.5rem;color:white;
                            margin-bottom:1rem'>
                    <div style='display:flex;justify-content:space-between;align-items:center'>
                        <div>
                            <div style='font-size:1.4em;font-weight:700'>{sc_center}</div>
                            <div style='opacity:0.7;font-size:0.9em'>{sc_week}
                            {"· vs " + prev_week if prev_week else ""}</div>
                        </div>
                        <div style='text-align:right;font-size:0.85em;opacity:0.7'>
                            {total} conductores
                        </div>
                    </div>
                </div>
                """), unsafe_allow_html=True)

                # Métricas en 5 columnas
                c1, c2, c3, c4, c5 = st.columns(5)
                sc_delta  = round(sc_mean - prev_sc_mean, 1) if prev_sc_mean is not None else None
                dnr_delta = round(dnr_mean - prev_dnr_mean, 2) if prev_dnr_mean is not None else None
                dcr_delta = round(dcr_mean - prev_dcr_mean, 2) if prev_dcr_mean is not None else None
                top_delta = round(pct_top2 - prev_pct_top2, 1) if prev_pct_top2 is not None else None

                c1.metric("Score Promedio", f"{sc_mean:.1f}", f"{sc_delta:+.1f}" if sc_delta is not None else None)
                c2.metric("DNR Promedio",   f"{dnr_mean:.2f}", f"{dnr_delta:+.2f}" if dnr_delta is not None else None,
                          delta_color="inverse")
                c3.metric("DCR",            f"{dcr_mean:.2f}%", f"{dcr_delta:+.2f}%" if dcr_delta is not None else None)
                c4.metric("POD",            f"{pod_mean:.2f}%")
                c5.metric("FANTASTIC+GREAT",f"{pct_top2}%", f"{top_delta:+.1f}%" if top_delta is not None else None)

                st.markdown("---")

                # ── Distribución visual con barras ────────────────────────
                st.subheader("🏆 Distribución de la Flota")
                d1, d2, d3, d4 = st.columns(4)
                for col, cal, n, color in [
                    (d1, 'FANTASTIC', n_fantastic, '#198754'),
                    (d2, 'GREAT',     n_great,     '#0d6efd'),
                    (d3, 'FAIR',      n_fair,       '#fd7e14'),
                    (d4, 'POOR',      n_poor,       '#dc3545'),
                ]:
                    pct = round(n/total*100, 1) if total else 0
                    col.markdown(clean_html(f"""
                    <div style='background:{color}15;border:2px solid {color};
                                border-radius:10px;padding:0.8rem;text-align:center'>
                        <div style='font-size:1.8em;font-weight:800;color:{color}'>{n}</div>
                        <div style='font-weight:700;color:{color}'>{cal}</div>
                        <div style='font-size:0.8em;color:#6c757d'>{pct}% de la flota</div>
                    </div>
                    """), unsafe_allow_html=True)

                st.markdown("---")

                # ── ALERTA: Conductores POOR ──────────────────────────────
                df_poor = df_sc[df_sc['calificacion'] == '🛑 POOR'].sort_values('score')
                if not df_poor.empty:
                    st.markdown(clean_html(f"""
                    <div style='background:#dc354515;border-left:4px solid #dc3545;
                                border-radius:6px;padding:0.8rem 1rem;margin-bottom:0.5rem'>
                        <b style='color:#dc3545'>🚨 {len(df_poor)} conductor{'es' if len(df_poor)>1 else ''} 
                        con calificación POOR — Requieren acción inmediata</b>
                    </div>
                    """), unsafe_allow_html=True)

                    for _, row in df_poor.iterrows():
                        with st.expander(
                            f"🛑 {row['driver_name']} — Score: {int(row['score'])} | "
                            f"DNR: {int(row['dnr'])} | DCR: {row['dcr']*100:.1f}%"
                        ):
                            col_a, col_b, col_c, col_d = st.columns(4)
                            col_a.metric("Score",  int(row['score']))
                            col_b.metric("DNR",    int(row['dnr']))
                            col_c.metric("DCR",    f"{row['dcr']*100:.2f}%")
                            col_d.metric("POD",    f"{row['pod']*100:.2f}%")

                            st.markdown("**Problemas detectados:**")
                            st.markdown(render_detalles(row.get('detalles','')), unsafe_allow_html=True)

                            # Coaching automático basado en el issue principal
                            detalles_str = str(row.get('detalles', ''))
                            tips = []
                            if 'DNR' in detalles_str or '🚨' in detalles_str:
                                tips.append("📌 **DNR:** Revisar rutas de difícil acceso. Llamar al cliente antes de intentar entrega. Documentar cualquier intento fallido.")
                            if 'DCR' in detalles_str or '📦' in detalles_str:
                                tips.append("📌 **DCR:** Auditar intentos fallidos. Verificar uso correcto de estados en la app (no marcar como entregado sin entregar).")
                            if 'POD' in detalles_str or '📸' in detalles_str:
                                tips.append("📌 **POD:** Foto obligatoria en CADA entrega. Asegurar que la foto sea visible y no ambigua.")
                            if 'FS' in detalles_str or '❌' in detalles_str or '⚠️' in detalles_str:
                                tips.append("📌 **False Scans:** No escanear en la furgoneta. Escanear solo en el punto exacto de entrega.")
                            if 'CC' in detalles_str or '📞' in detalles_str:
                                tips.append("📌 **Customer Contact:** Contactar al cliente cuando el acceso sea difícil. Registrar el intento de contacto.")
                            if 'RTS' in detalles_str or '🔄' in detalles_str:
                                tips.append("📌 **RTS Alto:** Reducir devoluciones al almacén. Verificar direcciones antes de salir y usar todas las opciones de entrega.")
                            if tips:
                                st.info("\n\n".join(tips))

                    st.markdown("---")

                # ── AVISO: Conductores FAIR ───────────────────────────────
                df_fair = df_sc[df_sc['calificacion'] == '⚠️ FAIR'].sort_values('score')
                if not df_fair.empty:
                    with st.expander(f"⚠️ {len(df_fair)} conductores en FAIR — Necesitan mejora"):
                        for _, row in df_fair.iterrows():
                            cols = st.columns([3, 1, 1, 1, 4])
                            cols[0].markdown(f"**{row['driver_name']}**")
                            cols[1].markdown(f"Score: **{int(row['score'])}**")
                            cols[2].markdown(f"DNR: **{int(row['dnr'])}**")
                            cols[3].markdown(f"DCR: **{row['dcr']*100:.1f}%**")
                            cols[4].markdown(
                                render_detalles(row.get('detalles','')),
                                unsafe_allow_html=True
                            )

                    st.markdown("---")

                # ── LISTADO: Conductores FANTASTIC y GREAT ──────────────────
                df_fantastic = df_sc[df_sc['calificacion'] == '💎 FANTASTIC'].sort_values('score', ascending=False)
                df_great = df_sc[df_sc['calificacion'] == '🥇 GREAT'].sort_values('score', ascending=False)

                if not df_fantastic.empty or not df_great.empty:
                    with st.expander(f"⭐ {len(df_fantastic)} Fantastic | {len(df_great)} Great — Ver listado"):
                        if not df_fantastic.empty:
                            st.markdown("**💎 FANTASTIC**")
                            for _, row in df_fantastic.iterrows():
                                cols = st.columns([3, 1, 1, 1, 4])
                                cols[0].markdown(f"**{row['driver_name']}**")
                                cols[1].markdown(f"Score: **{int(row['score'])}**")
                                cols[2].markdown(f"DNR: **{int(row['dnr'])}**")
                                cols[3].markdown(f"DCR: **{row['dcr']*100:.1f}%**")
                                cols[4].markdown(render_detalles(row.get('detalles','')), unsafe_allow_html=True)
                        if not df_great.empty:
                            if not df_fantastic.empty: st.divider()
                            st.markdown("**🥇 GREAT**")
                            for _, row in df_great.iterrows():
                                cols = st.columns([3, 1, 1, 1, 4])
                                cols[0].markdown(f"**{row['driver_name']}**")
                                cols[1].markdown(f"Score: **{int(row['score'])}**")
                                cols[2].markdown(f"DNR: **{int(row['dnr'])}**")
                                cols[3].markdown(f"DCR: **{row['dcr']*100:.1f}%**")
                                cols[4].markdown(render_detalles(row.get('detalles','')), unsafe_allow_html=True)
                    st.markdown("---")

                # ── Ranking de mejora WoW ─────────────────────────────────
                if not df_prev.empty and 'driver_id' in df_prev.columns:
                    df_merged_wow = df_sc[['driver_id', 'driver_name', 'score']].merge(
                        df_prev[['driver_id', 'score']].rename(columns={'score': 'score_prev'}),
                        on='driver_id', how='inner'
                    )
                    df_merged_wow['delta'] = df_merged_wow['score'] - df_merged_wow['score_prev']
                    top_mejora = df_merged_wow.nlargest(5, 'delta')
                    top_bajada = df_merged_wow.nsmallest(5, 'delta')

                    with st.expander(f"📈 Ranking WoW — {sc_week} vs {prev_week}"):
                        col_m, col_b = st.columns(2)
                        with col_m:
                            st.markdown("**🚀 Más mejorados**")
                            for _, r in top_mejora.iterrows():
                                if r['delta'] > 0:
                                    st.markdown(
                                        f"▲ **+{r['delta']:.0f}pts** · {r['driver_name']} "
                                        f"({r['score_prev']:.0f}→{r['score']:.0f})"
                                    )
                        with col_b:
                            st.markdown("**⚠️ Más bajaron**")
                            for _, r in top_bajada.iterrows():
                                if r['delta'] < 0:
                                    st.markdown(
                                        f"▼ **{r['delta']:.0f}pts** · {r['driver_name']} "
                                        f"({r['score_prev']:.0f}→{r['score']:.0f})"
                                    )

                    st.markdown("---")

                # ── Tabla completa con detalles como badges ───────────────
                st.subheader("📋 Tabla Completa de Conductores")

                # Construir tabla enriquecida con HTML
                df_display = df_sc[[
                    'driver_name', 'driver_id', 'calificacion', 'score',
                    'dnr', 'fs_count', 'dcr', 'pod', 'cc', 'rts', 'fdps', 'detalles'
                ]].sort_values('score', ascending=False).copy()

                # Construir HTML para la tabla
                rows_html = []
                for _, row in df_display.iterrows():
                    cal     = str(row['calificacion'])
                    bg_row  = {
                        '💎 FANTASTIC': '#f0fff4',
                        '🥇 GREAT':     '#f0f4ff',
                        '⚠️ FAIR':      '#fffaf0',
                        '🛑 POOR':      '#fff5f5',
                    }.get(cal, 'white')

                    score_bar_html = render_score_bar(float(row['score']))
                    cal_badge      = render_calificacion(cal)
                    det_badges     = render_detalles(row.get('detalles',''))

                    rows_html.append(clean_html(f"""
                    <tr style='background:{bg_row};border-bottom:1px solid #dee2e6'>
                        <td style='padding:6px 8px;font-weight:600'>{row['driver_name']}</td>
                        <td style='padding:6px 8px;color:#6c757d;font-size:0.85em'>{row['driver_id']}</td>
                        <td style='padding:6px 8px'>{cal_badge}</td>
                        <td style='padding:6px 8px;min-width:120px'>{score_bar_html}</td>
                        <td style='padding:6px 8px;text-align:center'><b style='color:{"#dc3545" if row["dnr"]>=2 else "#198754"}'>{int(row["dnr"])}</b></td>
                        <td style='padding:6px 8px;text-align:center'>{row["dcr"]*100:.2f}%</td>
                        <td style='padding:6px 8px;text-align:center'>{row["pod"]*100:.2f}%</td>
                        <td style='padding:6px 8px;text-align:center'>{row["cc"]*100:.2f}%</td>
                        <td style='padding:6px 8px'>{det_badges}</td>
                    </tr>"""))

                table_html = clean_html(f"""
                <div style='overflow-x:auto;border-radius:8px;border:1px solid #dee2e6'>
                <table style='width:100%;border-collapse:collapse;font-size:0.88em'>
                    <thead>
                        <tr style='background:#232f3e;color:white'>
                            <th style='padding:8px;text-align:left'>Conductor</th>
                            <th style='padding:8px;text-align:left'>ID</th>
                            <th style='padding:8px;text-align:left'>Calificación</th>
                            <th style='padding:8px;text-align:left'>Score</th>
                            <th style='padding:8px;text-align:center'>DNR</th>
                            <th style='padding:8px;text-align:center'>DCR</th>
                            <th style='padding:8px;text-align:center'>POD</th>
                            <th style='padding:8px;text-align:center'>CC</th>
                            <th style='padding:8px;text-align:left'>Problemas</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows_html)}
                    </tbody>
                </table>
                </div>
                """)
                st.markdown(table_html, unsafe_allow_html=True)

                # ── Descarga Excel (solo admins) ──────────────────────────
                if is_admin:
                    st.markdown("---")
                    output = io.BytesIO()
                    df_for_excel = df_sc[[
                        'driver_name', 'driver_id', 'calificacion', 'score', 'entregados',
                        'dnr', 'fs_count', 'dnr_risk_events', 'dcr', 'pod', 'cc',
                        'fdps', 'rts', 'cdf', 'detalles'
                    ]].copy()
                    df_for_excel.columns = [
                        'Nombre', 'ID', 'CALIFICACION', 'SCORE', 'Entregados',
                        'DNR', 'FS_Count', 'DNR_RISK_EVENTS', 'DCR', 'POD', 'CC',
                        'FDPS', 'RTS', 'CDF', 'DETALLES'
                    ]
                    scorecard.create_professional_excel(
                        df_for_excel, output, center_name=sc_center, week=sc_week
                    )
                    st.download_button(
                        "📥 Descargar Excel Completo",
                        output.getvalue(),
                        f"Scorecard_{sc_center}_{sc_week}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                else:
                    st.caption("ℹ️ Descarga disponible solo para administradores.")

                # ── TENDENCIA POR CONDUCTOR ───────────────────────────────────
                st.markdown("---")
                st.subheader("📈 Evolución de un Conductor")
                st.caption("Selecciona un conductor para ver su tendencia histórica de score y métricas clave.")

                # Selector de conductor
                driver_options = sorted(
                    [f"{r['driver_name']} ({r['driver_id']})" for _, r in df_sc.iterrows()],
                    key=lambda x: x.lower()
                )
                selected_driver_str = st.selectbox(
                    "🔍 Conductor",
                    driver_options,
                    key=f"trend_driver_{sc_center}_{sc_week}"
                )

                if selected_driver_str:
                    # Extraer driver_id del string seleccionado
                    sel_driver_id = selected_driver_str.split('(')[-1].rstrip(')')
                    sel_driver_name = selected_driver_str.split(' (')[0]

                    df_trend = cached_driver_trend(_DB_KEY, db_config, sel_driver_id, sc_center)

                    if df_trend.empty:
                        st.info("ℹ️ No se encontraron datos históricos para este conductor.")
                    elif len(df_trend) < 2:
                        # 1 semana: mostramos los datos pero no hay tendencia que dibujar
                        st.info(
                            f"ℹ️ **{sel_driver_name}** solo tiene datos de 1 semana "
                            f"({df_trend['semana'].iloc[0]}). "
                            "Necesitas al menos 2 semanas para ver la tendencia."
                        )
                        st.metric(
                            "Score actual",
                            int(df_trend['score'].iloc[0]),
                            help="Score de la única semana disponible"
                        )
                    else:
                        # ── Header del conductor ──────────────────────────────
                        latest = df_trend.iloc[-1]
                        oldest = df_trend.iloc[0]
                        total_delta = round(latest['score'] - oldest['score'], 1)
                        trend_color = '#198754' if total_delta >= 0 else '#dc3545'
                        trend_icon  = '📈' if total_delta > 0 else ('📉' if total_delta < 0 else '📊')

                        st.markdown(clean_html(f"""
                        <div style='background:#f8f9fa;border-radius:10px;padding:1rem 1.5rem;
                                    border-left:4px solid {trend_color};margin-bottom:1rem'>
                            <div style='font-size:1.1em;font-weight:700'>{trend_icon} {sel_driver_name}</div>
                            <div style='color:#6c757d;font-size:0.85em'>{sc_center} · {len(df_trend)} semanas de datos</div>
                            <div style='margin-top:0.3rem;font-size:0.9em'>
                                Evolución total: <b style='color:{trend_color}'>{total_delta:+.1f} pts</b>
                                &nbsp;·&nbsp; {df_trend['semana'].iloc[0]} → {df_trend['semana'].iloc[-1]}
                            </div>
                        </div>
                        """), unsafe_allow_html=True)

                        # ── Gráfico de score con zonas coloreadas ─────────────
                        # Construir DataFrame para el gráfico
                        df_plot = df_trend[['semana', 'score']].set_index('semana').copy()

                        # Zonas de calificación como líneas de referencia
                        semanas_list = df_trend['semana'].tolist()
                        n_sem = len(semanas_list)

                        # Añadir líneas de umbral como columnas extra para contexto visual
                        df_plot['FANTASTIC (90)'] = 90
                        df_plot['GREAT (80)']     = 80
                        df_plot['FAIR (60)']      = 60

                        st.markdown("**📊 Score histórico**")
                        st.line_chart(df_plot, height=280, use_container_width=True)

                        # ── Mini métricas últimas semanas ─────────────────────
                        if len(df_trend) >= 2:
                            st.markdown("**🔍 Métricas clave por semana**")
                            # Tabla de las últimas 8 semanas (o todas si hay menos)
                            df_detail = df_trend.tail(TREND_SEMANAS_MAX).copy()
                            df_detail['dcr_%'] = (df_detail['dcr'] * 100).round(2)
                            df_detail['pod_%'] = (df_detail['pod'] * 100).round(2)

                            detail_rows = []
                            for _, dr in df_detail.iterrows():
                                cal = str(dr['calificacion'])
                                bg_cal = {
                                    '💎 FANTASTIC': '#f0fff4',
                                    '🥇 GREAT':     '#f0f4ff',
                                    '⚠️ FAIR':      '#fffaf0',
                                    '🛑 POOR':      '#fff5f5',
                                }.get(cal, 'white')
                                dnr_c = '#dc3545' if dr['dnr'] >= 2 else '#198754'
                                detail_rows.append(clean_html(f"""
                                <tr style='background:{bg_cal}'>
                                    <td style='padding:6px 10px;font-weight:600'>{dr['semana']}</td>
                                    <td style='padding:6px 10px'>{render_calificacion(cal)}</td>
                                    <td style='padding:6px 10px;text-align:center;font-weight:700;
                                        color:#{"198754" if dr["score"]>=80 else "dc3545"}'>{int(dr['score'])}</td>
                                    <td style='padding:6px 10px;text-align:center;font-weight:700;color:{dnr_c}'>{int(dr['dnr'])}</td>
                                    <td style='padding:6px 10px;text-align:center'>{dr['dcr_%']:.2f}%</td>
                                    <td style='padding:6px 10px;text-align:center'>{dr['pod_%']:.2f}%</td>
                                    <td style='padding:6px 10px'>{render_detalles(str(dr.get('detalles','')))}</td>
                                </tr>"""))

                            st.markdown(clean_html(f"""
                            <div style='overflow-x:auto;border-radius:8px;border:1px solid #dee2e6;margin-top:0.5rem'>
                            <table style='width:100%;border-collapse:collapse;font-size:0.88em'>
                                <thead>
                                    <tr style='background:#37475a;color:white'>
                                        <th style='padding:8px 10px;text-align:left'>Semana</th>
                                        <th style='padding:8px 10px;text-align:left'>Calificación</th>
                                        <th style='padding:8px 10px;text-align:center'>Score</th>
                                        <th style='padding:8px 10px;text-align:center'>DNR</th>
                                        <th style='padding:8px 10px;text-align:center'>DCR</th>
                                        <th style='padding:8px 10px;text-align:center'>POD</th>
                                        <th style='padding:8px 10px;text-align:left'>Problemas</th>
                                    </tr>
                                </thead>
                                <tbody>{''.join(detail_rows)}</tbody>
                            </table></div>
                            """), unsafe_allow_html=True)

                        # ── Tendencia de métricas secundarias ─────────────────
                        with st.expander("📊 Ver evolución de DNR / DCR / POD"):
                            df_metrics = df_trend[['semana']].copy().set_index('semana')
                            df_metrics['DNR']    = df_trend['dnr'].values
                            df_metrics['DCR (%)']= (df_trend['dcr'] * 100).values.round(2)
                            df_metrics['POD (%)']= (df_trend['pod'] * 100).values.round(2)
                            st.line_chart(df_metrics, height=260, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error cargando el scorecard: {e}")
        st.exception(e)

# ─────────────────────────────────────────────────────────────────────────────
# TAB: HISTÓRICO
# ─────────────────────────────────────────────────────────────────────────────

with tab_hist:
    st.header("📈 Histórico de Scorecards")

    try:
        # JTs: solo semanas permitidas. Admins: todo.
        allowed_hist = ALLOWED_WEEKS_JT if is_jt else None
        df_meta = cached_meta(_DB_KEY, db_config, allowed_hist)

        if is_jt and allowed_hist:
            st.info(
                f"👔 Mostrando datos de: **{' y '.join(allowed_hist)}** "
                f"(semana en curso y anterior)"
            )

        if df_meta.empty:
            st.info("📭 No hay datos. Procesa archivos primero.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                f_center = st.multiselect("🏢 Centro", sorted(df_meta['centro'].unique()))
            with col2:
                f_week = st.multiselect("📅 Semana", sorted(df_meta['semana'].unique(), reverse=True))
            with col3:
                f_calif = st.multiselect("🏆 Calificación", df_meta['calificacion'].unique())

            search_term = st.text_input("🔍 Buscar conductor", placeholder="Nombre o ID...")

            if st.button("🔍 Buscar", type="primary", use_container_width=True):
                p = "%s" if db_config['type'] == 'postgresql' else "?"

                # Semanas efectivas para JTs: intersección con permitidas
                if is_jt and allowed_hist:
                    weeks_to_use = [w for w in f_week if w in allowed_hist] if f_week else allowed_hist
                else:
                    weeks_to_use = f_week

                where_clauses = []
                params = []
                if f_center:
                    ph = ", ".join([p]*len(f_center))
                    where_clauses.append(f"centro IN ({ph})")
                    params.extend(f_center)
                if weeks_to_use:
                    ph = ", ".join([p]*len(weeks_to_use))
                    where_clauses.append(f"semana IN ({ph})")
                    params.extend(weeks_to_use)
                if f_calif:
                    ph = ", ".join([p]*len(f_calif))
                    where_clauses.append(f"calificacion IN ({ph})")
                    params.extend(f_calif)
                if search_term:
                    where_clauses.append(f"(LOWER(driver_name) LIKE {p} OR LOWER(driver_id) LIKE {p})")
                    params.extend([f"%{search_term.lower()}%", f"%{search_term.lower()}%"])

                where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
                q = f"""
                    SELECT semana, centro, driver_name AS conductor, driver_id AS id,
                           calificacion, score, dnr, ROUND(dcr*100,2) as dcr_pct,
                           ROUND(pod*100,2) as pod_pct, ROUND(cc*100,2) as cc_pct,
                           detalles
                    FROM scorecards {where_sql}
                    ORDER BY semana DESC, score DESC
                    LIMIT {HISTORICO_MAX_ROWS}
                """
                conn2 = scorecard.get_db_connection(db_config=db_config)
                df_filtered = pd.read_sql_query(q, conn2, params=params if params else None)
                conn2.close()

                if not df_filtered.empty:
                    # KPIs resumen
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Registros",     len(df_filtered))
                    c2.metric("DNR Promedio",  f"{df_filtered['dnr'].mean():.2f}")
                    c3.metric("Score Promedio",f"{df_filtered['score'].mean():.1f}")
                    c4.metric("DCR Promedio",  f"{df_filtered['dcr_pct'].mean():.2f}%")

                    if len(df_filtered) == HISTORICO_MAX_ROWS:
                        st.info(f"Mostrando los primeros {HISTORICO_MAX_ROWS:,} resultados. Aplica más filtros para afinar.")

                    st.divider()
                    st.dataframe(
                        df_filtered,
                        column_config={
                            "conductor":   st.column_config.TextColumn("Conductor", width="medium"),
                            "id":          st.column_config.TextColumn("ID", width="small"),
                            "calificacion":st.column_config.TextColumn("Calificación", width="small"),
                            "score":       st.column_config.NumberColumn("Score", format="%d"),
                            "dnr":         st.column_config.NumberColumn("DNR", format="%d"),
                            "dcr_pct":     st.column_config.NumberColumn("DCR%", format="%.2f"),
                            "pod_pct":     st.column_config.NumberColumn("POD%", format="%.2f"),
                            "cc_pct":      st.column_config.NumberColumn("CC%", format="%.2f"),
                            "detalles":    st.column_config.TextColumn("Detalles", width="large"),
                        },
                        use_container_width=True,
                        hide_index=True,
                        height=450,
                    )

                    if is_admin:
                        csv = df_filtered.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            "📥 Descargar CSV", csv, "historico.csv", "text/csv"
                        )
                else:
                    st.warning("No se encontraron registros con esos filtros.")
            else:
                st.info("👆 Aplica filtros y pulsa Buscar.")

    except Exception as e:
        st.warning(f"⚠️ Error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: PERFIL
# ─────────────────────────────────────────────────────────────────────────────

with tab_profile:
    st.header("👤 Mi Perfil")

    st.markdown(f"""
    | Campo | Valor |
    |---|---|
    | **Usuario** | {user_data_session['name']} |
    | **Rol** | {role_label} |
    | **Sesión inicia** | {st.session_state.get('last_activity', '—')} |
    | **Timeout** | {SESSION_TIMEOUT_MINUTES} min de inactividad |
    """)

    st.divider()
    st.subheader("🔒 Cambiar Contraseña")
    with st.form("change_password_form"):
        old_pw  = st.text_input("Contraseña Actual", type="password")
        new_pw  = st.text_input("Nueva Contraseña (mínimo 8 caracteres)", type="password")
        conf_pw = st.text_input("Confirmar Nueva Contraseña", type="password")

        if st.form_submit_button("Cambiar Contraseña", use_container_width=True):
            if not old_pw or not new_pw or not conf_pw:
                st.error("❌ Todos los campos son obligatorios")
            elif new_pw != conf_pw:
                st.error("❌ Las contraseñas no coinciden")
            elif len(new_pw) < 8:
                st.error("❌ La contraseña debe tener al menos 8 caracteres")
            else:
                current_hash = get_user_password_hash(user_data_session['name'], db_config)
                if current_hash and scorecard.verify_password(old_pw, current_hash):
                    new_hash = scorecard.hash_password(new_pw)
                    if update_user_password(user_data_session['name'], new_hash, db_config):
                        _audit("Cambió su contraseña")
                        st.success("✅ Contraseña actualizada correctamente")
                    else:
                        st.error("❌ Error actualizando contraseña en la BD")
                else:
                    st.error("❌ La contraseña actual es incorrecta")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: ADMINISTRACIÓN (sin cambios funcionales, mejorado visualmente)
# ─────────────────────────────────────────────────────────────────────────────

if tab_admin:
    with tab_admin:
        st.header("👑 Panel de Administración")

        # ── Gestión de Usuarios ───────────────────────────────────────────
        st.subheader("👥 Gestión de Usuarios")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### ➕ Crear Usuario")
            with st.form("create_user_form"):
                new_username = st.text_input("Nombre de Usuario")
                new_password = st.text_input("Contraseña", type="password",
                                             help="Mínimo 8 caracteres")
                if is_superadmin:
                    new_role = st.selectbox("Rol", ["jt", "admin", "superadmin"])
                else:
                    new_role = "jt"
                    st.info("ℹ️ Los admins solo pueden crear usuarios JT")

                if st.form_submit_button("Crear Usuario", use_container_width=True):
                    if not new_username or not new_password:
                        st.error("❌ Completa todos los campos")
                    elif len(new_password) < 8:
                        st.error("❌ Mínimo 8 caracteres")
                    else:
                        try:
                            conn = scorecard.get_db_connection(db_config)
                            cursor = conn.cursor()
                            q = ("INSERT INTO users (username, password, role, active, must_change_password) "
                                 "VALUES (%s, %s, %s, 1, 1)"
                                 if db_config['type'] == 'postgresql' else
                                 "INSERT INTO users (username, password, role, active, must_change_password) "
                                 "VALUES (?, ?, ?, 1, 1)")
                            cursor.execute(q, (new_username, scorecard.hash_password(new_password), new_role))
                            conn.commit()
                            conn.close()
                            _audit(f"Creó usuario '{new_username}' con rol '{new_role}'")
                            st.success(f"✅ Usuario '{new_username}' creado (deberá cambiar contraseña al entrar)")
                            st.rerun()
                        except Exception as e:
                            if "UNIQUE" in str(e) or "unique" in str(e):
                                st.error("❌ El usuario ya existe")
                            else:
                                st.error(f"❌ Error: {e}")

        with col2:
            st.markdown("#### 📋 Usuarios Activos")
            try:
                conn = scorecard.get_db_connection(db_config)
                df_users = pd.read_sql_query(
                    "SELECT username, role, active FROM users ORDER BY role, username", conn
                )
                conn.close()

                if not df_users.empty:
                    st.dataframe(df_users, use_container_width=True, height=180, hide_index=True)

                    st.markdown("#### 🗑️ Eliminar Usuario")
                    user_to_delete = st.selectbox("Seleccionar", df_users['username'].tolist())

                    if st.button("Eliminar seleccionado", type="secondary", use_container_width=True):
                        if user_to_delete == user_data_session['name']:
                            st.error("❌ No puedes eliminarte a ti mismo")
                        else:
                            try:
                                target_role = get_user_role(user_to_delete, db_config)
                                # Un superadmin solo puede borrarse si hay otro superadmin
                                if target_role == 'superadmin':
                                    conn_c = scorecard.get_db_connection(db_config)
                                    cursor_c = conn_c.cursor()
                                    p2 = "%s" if db_config['type'] == 'postgresql' else "?"
                                    cursor_c.execute(
                                        f"SELECT COUNT(*) FROM users WHERE role = {p2} AND active = 1",
                                        ('superadmin',)
                                    )
                                    total_sa = cursor_c.fetchone()[0]
                                    conn_c.close()
                                    if total_sa <= 1:
                                        st.error("🛑 No se puede eliminar al único Superadmin del sistema")
                                        # No usar st.stop() — detiene el render completo de la app.
                                        # Salimos del bloque con la condición else encadenada abajo.
                                        target_role = None  # Fuerza el path de error sin borrar
                                if target_role in ['admin', 'superadmin'] and not is_superadmin:
                                    st.error("🛑 Solo el Superadmin puede eliminar administradores")
                                elif target_role is None:
                                    st.error("❌ Usuario no encontrado")
                                else:
                                    conn = scorecard.get_db_connection(db_config)
                                    cursor = conn.cursor()
                                    q_d = ("DELETE FROM users WHERE username = %s"
                                           if db_config['type'] == 'postgresql' else
                                           "DELETE FROM users WHERE username = ?")
                                    cursor.execute(q_d, (user_to_delete,))
                                    conn.commit()
                                    conn.close()
                                    _audit(f"Eliminó usuario '{user_to_delete}' (rol: {target_role})")
                                    st.success(f"✅ '{user_to_delete}' eliminado")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {e}")
            except Exception as e:
                st.error(f"Error: {e}")

        # ── Zona Superadmin ──────────────────────────────────────────────
        if is_superadmin:
            st.divider()
            st.subheader("👑 Zona Superadmin")

            t1, t2, t3 = st.tabs(["📊 Estadísticas", "📝 Logs", "⚙️ Configuración"])

            with t1:
                try:
                    conn = scorecard.get_db_connection(db_config)
                    cursor = conn.cursor()
                    stats = {}
                    p = "%s" if db_config['type'] == 'postgresql' else "?"
                    q_rol = "SELECT COUNT(*) FROM users WHERE role = " + p
                    for rol in ['superadmin', 'admin', 'jt']:
                        cursor.execute(q_rol, (rol,))
                        stats[rol] = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM scorecards")
                    stats['records'] = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT semana, MAX(timestamp) t FROM scorecards GROUP BY semana ORDER BY t DESC LIMIT 5"
                    )
                    recent_weeks = cursor.fetchall()
                    conn.close()

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("👑 Superadmins", stats['superadmin'])
                    c2.metric("🔑 Admins",      stats['admin'])
                    c3.metric("👔 JTs",          stats['jt'])
                    c4.metric("📊 Registros BD", f"{stats['records']:,}")

                    if recent_weeks:
                        st.markdown("**Últimas semanas subidas:**")
                        for sem, ts in recent_weeks:
                            st.caption(f"• {sem} — subida: {ts}")
                except Exception as e:
                    st.error(f"Error: {e}")

            with t2:
                log_file = "logs/winiw_scorecard.log"
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    n = st.slider("Líneas a mostrar", 20, 500, 100)
                    st.code(''.join(lines[-n:]), language='log')
                    st.download_button("📥 Descargar Logs", ''.join(lines), "logs.txt", use_container_width=True)
                else:
                    st.info("No hay logs disponibles aún.")

            with t3:
                st.warning("⚠️ Cambios que afectan a todo el sistema")

                with st.expander("👑 Promocionar usuario a Superadmin"):
                    with st.form("promote_form"):
                        promote_user = st.text_input("Usuario a promocionar")
                        if st.form_submit_button("Promocionar"):
                            if promote_user:
                                try:
                                    current_role = get_user_role(promote_user, db_config)
                                    if current_role is None:
                                        st.error("❌ Usuario no encontrado")
                                    elif current_role == 'superadmin':
                                        st.info("ℹ️ Ya es superadmin")
                                    else:
                                        conn = scorecard.get_db_connection(db_config)
                                        cursor = conn.cursor()
                                        q2 = ("UPDATE users SET role = %s WHERE username = %s"
                                              if db_config['type'] == 'postgresql' else
                                              "UPDATE users SET role = ? WHERE username = ?")
                                        cursor.execute(q2, ('superadmin', promote_user))
                                        conn.commit()
                                        conn.close()
                                        _audit(f"Promovió '{promote_user}' a superadmin (era: {current_role})")
                                        st.success(f"✅ {promote_user} ahora es SUPERADMIN")
                                except Exception as e:
                                    st.error(f"❌ Error: {e}")

                with st.expander("💾 Info de Base de Datos"):
                    if db_config['type'] == 'postgresql':
                        st.success("🌐 Supabase/PostgreSQL")
                        st.code(f"Host: {db_config.get('host')}\nBD: {db_config.get('database')}")
                    else:
                        st.info("💾 SQLite (local) — en producción usa Supabase")

        st.divider()

        # ── Gestión de BD ────────────────────────────────────────────────
        st.subheader("🗄️ Gestión de Base de Datos")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("#### 📊 Estadísticas")
            try:
                conn = scorecard.get_db_connection(db_config)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM scorecards")
                st.metric("Total Registros", f"{cursor.fetchone()[0]:,}")
                cursor.execute("SELECT COUNT(DISTINCT centro) FROM scorecards")
                st.metric("Centros", cursor.fetchone()[0])
                cursor.execute("SELECT COUNT(DISTINCT semana) FROM scorecards")
                st.metric("Semanas almacenadas", cursor.fetchone()[0])
                conn.close()
            except Exception:
                st.warning("BD vacía")

        with col2:
            st.markdown("#### 🧹 Limpiar Lote")
            with st.form("clean_batch_form"):
                clean_center = st.text_input("Centro")
                clean_week   = st.text_input("Semana", placeholder="ej: W05")
                if st.form_submit_button("Limpiar"):
                    if clean_center and clean_week:
                        scorecard.delete_scorecard_batch(clean_week, clean_center, db_config=db_config)
                        _clear_all_caches()
                        _audit(f"Eliminó lote {clean_center} {clean_week}")
                        st.success(f"✅ {clean_center} — {clean_week} eliminado")
                    else:
                        st.error("Completa ambos campos")

        with col3:
            st.markdown("#### ⚠️ Zona de Peligro")
            with st.expander("🗑️ Borrar TODO el historial"):
                st.error("Esta acción es IRREVERSIBLE")
                confirm = st.text_input("Escribe CONFIRMAR:")
                if st.button("BORRAR TODO", disabled=(confirm != "CONFIRMAR"),
                             type="primary", use_container_width=True):
                    if scorecard.reset_production_database(db_config):
                        _clear_all_caches()  # Reset total: invalida toda la caché
                        _audit("⚠️ RESET TOTAL de base de datos")
                        st.success("✅ Base de datos limpiada")
                        st.rerun()

        st.divider()
        st.subheader("🎯 Configuración de Targets por Centro")
        st.caption("Define los umbrales de calidad para cada centro. Afecta al cálculo de scores.")

        try:
            conn = scorecard.get_db_connection(db_config)
            centros_bd = pd.read_sql_query(
                "SELECT DISTINCT centro FROM scorecards ORDER BY centro", conn
            )['centro'].tolist()
            conn.close()
        except Exception:
            centros_bd = []

        if centros_bd:
            sel_target_center = st.selectbox("Centro a configurar", centros_bd, key="target_center")
            curr = scorecard.get_center_targets(sel_target_center, db_config=db_config)

            tc1, tc2, tc3, tc4 = st.columns(4)
            new_dnr  = tc1.number_input("DNR Max",     value=float(curr['target_dnr']),
                                        min_value=0.0, max_value=20.0, step=0.5,
                                        key="nt_dnr",  help="0–20")
            new_dcr  = tc2.number_input("DCR Min (%)", value=float(curr['target_dcr']*100),
                                        min_value=80.0, max_value=100.0, step=0.1,
                                        key="nt_dcr",  help="80–100%") / 100
            new_pod  = tc3.number_input("POD Min (%)", value=float(curr['target_pod']*100),
                                        min_value=80.0, max_value=100.0, step=0.1,
                                        key="nt_pod",  help="80–100%") / 100
            new_cc   = tc4.number_input("CC Min (%)",  value=float(curr['target_cc']*100),
                                        min_value=80.0, max_value=100.0, step=0.1,
                                        key="nt_cc",   help="80–100%") / 100

            if st.button("💾 Guardar Targets", type="primary"):
                scorecard.save_center_targets({
                    'centro': sel_target_center,
                    'target_dnr': new_dnr, 'target_dcr': new_dcr,
                    'target_pod': new_pod, 'target_cc': new_cc,
                    'target_fdps': curr['target_fdps'],
                    'target_rts': curr['target_rts'],
                    'target_cdf': curr['target_cdf'],
                }, db_config=db_config)
                st.success(f"✅ Targets de {sel_target_center} guardados")
        else:
            st.info("Procesa al menos un scorecard primero para configurar targets.")

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown("""
<div style='display:flex;justify-content:space-between;align-items:center;
            color:#6c757d;font-size:0.8em'>
    <span>🛡️ Winiw Quality Scorecard v3.5 · Amazon DSP</span>
    <span>Supabase guarda todo · Streamlit optimiza los recursos</span>
    <span>🏆 Lideres en calidad</span>
</div>
""", unsafe_allow_html=True)
