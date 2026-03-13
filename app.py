"""
Winiw Quality Scorecard — app.py v3.9
======================================
v3.3: Dashboard rediseñado, caché, JT restrictions, DSP PDF parser, WoW deltas
v3.4: SQL injection fix, hardcoding eliminado, caché selectivo, audit log, validaciones
v3.7 (este archivo):
  - 🔒 SEGURIDAD: Rate limiting en login — 5 intentos fallidos → bloqueo 15 min
  - 🏢 NUEVO TAB: Dashboard Ejecutivo — todos los centros en una pantalla, ranking, WoW
  - 📈 TENDENCIA: Gráfico de evolución del score por conductor (últimas 8 semanas)
  - 📊 TENDENCIA: Líneas de DNR, DCR, POD para análisis de causas raíz
  - 🎨 UX: Zonas de referencia en gráfico (FANTASTIC/GREAT/FAIR) para contexto visual
  - 🧹 CÓDIGO: Helper get_user_role() — elimina última query duplicada del admin
  - 🧹 CÓDIGO: st.write() → st.markdown() en todo el archivo
  - 📊 CÓDIGO: SEMANAS_VISIBLES_JT y TREND_SEMANAS_MAX como constantes configurables
"""

import streamlit as st
import pandas as pd
import zipfile
import tempfile
import pathlib
import amazon_scorecard_ultra_robust_v3_FINAL as scorecard
import io
import re
import os
import logging
import html as _html
import altair as alt
from datetime import datetime, timedelta

# Logger de auditoría de la app (separado del motor)
_log = logging.getLogger("winiw_app")
if not _log.handlers:
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/winiw_app.log", mode='a', encoding='utf-8'),
        ]
    )

def _audit(msg: str):
    """Log de auditoría: registra quién hizo qué y cuándo."""
    user = st.session_state.get("user", {}).get("name", "anon")
    _log.info(f"[{user}] {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMITING (persistente vía BD — funciona en multi-worker y tras reinicios)
# ─────────────────────────────────────────────────────────────────────────────
# Se delega completamente al motor (scorecard.py) que usa la tabla login_attempts.
# Estas constantes se pasan como parámetros a las funciones del motor.
MAX_LOGIN_ATTEMPTS    = 5        # intentos fallidos antes del bloqueo
LOGIN_LOCKOUT_MINUTES = 15       # minutos de bloqueo tras agotar intentos

# ─────────────────────────────────────────────────────────────────────────────
# BOOTSTRAP: propagar st.secrets → os.environ para el motor (Streamlit Cloud)
# ─────────────────────────────────────────────────────────────────────────────
try:
    for _k in ("WINIW_ADMIN_USER", "WINIW_ADMIN_PASS"):
        if _k not in os.environ:
            _v = st.secrets.get(_k) or st.secrets.get("app", {}).get(_k)
            if _v:
                os.environ[_k] = str(_v)
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG INICIAL
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Winiw Quality Scorecard",
    layout="wide",
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

SESSION_TIMEOUT_MINUTES = 60
HISTORICO_MAX_ROWS     = 2000  # Reducido para rendimiento
SEMANAS_VISIBLES_JT    = 2
TREND_SEMANAS_MAX      = 8
TREND_WEEKS_BATCH      = 4    # Semanas cargadas en batch para trend conductores
SEMANAS_RECIENTES      = 5    # Semanas recientes en selector de semana activa
MAX_SEMANAS_ACTIVAS    = 4     # Semanas activas en vistas principales (BD guarda todo)
DRIVERS_PER_PAGE       = 20   # Conductores por página en tab Scorecard

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
    now = datetime.now()
    last = st.session_state.get("last_activity")
    if last is None:
        st.session_state["last_activity"] = now
        return
    if (now - last) > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
        st.session_state.clear()
        st.warning("⏰ Sesión expirada por inactividad. Inicia sesión de nuevo.")
        st.stop()
    st.session_state["last_activity"] = now


def clean_html(html: str) -> str:
    """Elimina toda la indentación de cada línea para evitar que Markdown lo tome como código."""
    if not html: return ""
    return "\n".join([line.strip() for line in html.split("\n")])


# ── Caché de datos (TTL 5 min para no saturar Supabase) ──────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_active_weeks(_db_config_key: str, db_config: dict, limit: int = MAX_SEMANAS_ACTIVAS) -> list:
    """
    Devuelve las últimas `limit` semanas por timestamp de subida.
    Usado para filtrar las vistas principales (Scorecard, Dashboard) y para JT.
    La BD sigue guardando TODO — esto es solo un filtro de visualización.
    """
    try:
        with scorecard.db_connection(db_config) as conn:
            df = pd.read_sql_query(
                "SELECT semana, MAX(timestamp) as last_upload "
                "FROM scorecards GROUP BY semana ORDER BY last_upload DESC"
                f" LIMIT {limit}",
                conn
            )
        return df['semana'].tolist()
    except Exception as _e:
        _log.warning(f"get_active_weeks: {_e}")
        return []


def cached_allowed_weeks_jt(_db_config_key: str, db_config: dict) -> list:
    """Las 2 semanas que puede ver un JT — delega a get_active_weeks."""
    return get_active_weeks(_db_config_key, db_config, limit=SEMANAS_VISIBLES_JT)


@st.cache_data(ttl=300, show_spinner=False)
def cached_scorecard(_db_config_key: str, db_config: dict, semana: str, centro: str) -> pd.DataFrame:
    """Carga datos de un lote con caché de 5 min."""
    try:
        with scorecard.db_connection(db_config) as conn:
            p = "%s" if db_config['type'] == 'postgresql' else "?"
            df = pd.read_sql_query(
                f"""SELECT id, semana, fecha_semana, centro, driver_id, driver_name,
                           calificacion, score, entregados, dnr, fs_count,
                           dnr_risk_events, dcr, pod, cc, fdps, rts, cdf,
                           entregados_oficial, dcr_oficial, pod_oficial, cc_oficial,
                           dsc_dpmo, lor_dpmo, ce_dpmo, cdf_dpmo_oficial, pdf_loaded,
                           uploaded_by, timestamp
                    FROM scorecards WHERE semana = {p} AND centro = {p}""",
                conn, params=(semana, centro)
            )
        return df
    except Exception as _e:
        _log.warning(f"cached_scorecard error: {_e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def cached_available_batches(_db_config_key: str, db_config: dict,
                              allowed_weeks: list = None,
                              active_weeks_only: list = None) -> pd.DataFrame:
    """
    Lista de lotes disponibles.
    - allowed_weeks: filtro de JT (solo sus semanas permitidas)
    - active_weeks_only: filtro de vistas principales (últimas 4 semanas)
    - Si ninguno se pasa → devuelve TODO (para Histórico)
    """
    try:
        with scorecard.db_connection(db_config) as conn:
            where_parts = []
            params = []
            p = "%s" if db_config['type'] == 'postgresql' else "?"

            if active_weeks_only:
                phs = ", ".join([p] * len(active_weeks_only))
                where_parts.append(f"semana IN ({phs})")
                params += list(active_weeks_only)
            if allowed_weeks:
                phs = ", ".join([p] * len(allowed_weeks))
                where_parts.append(f"semana IN ({phs})")
                params += list(allowed_weeks)

            where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
            q = f"""
                SELECT semana, centro,
                       MAX(uploaded_by) as subido_por,
                       MAX(timestamp) as fecha_subida
                FROM scorecards {where}
                GROUP BY semana, centro
                ORDER BY fecha_subida DESC
            """
            df = pd.read_sql_query(q, conn, params=params if params else None)
        return df
    except Exception as _e:
        _log.warning(f"cached_available_batches error: {_e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def cached_meta(_db_config_key: str, db_config: dict, allowed_weeks: list = None) -> pd.DataFrame:
    """Metadatos para filtros del histórico."""
    try:
        with scorecard.db_connection(db_config) as conn:
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
        return df
    except Exception as _e:
        _log.warning(f"cached_meta error: {_e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def cached_driver_trend(_db_config_key: str, db_config: dict, driver_id: str, centro: str) -> pd.DataFrame:
    """
    Tendencia histórica de un conductor — todas las semanas disponibles para ese centro.
    Devuelve columnas: semana, score, dnr, dcr, pod, cc, calificacion
    """
    try:
        with scorecard.db_connection(db_config) as conn:
            p = "%s" if db_config['type'] == 'postgresql' else "?"
            df = pd.read_sql_query(
                f"""SELECT semana, score, dnr, dcr, pod, cc, calificacion, detalles
                    FROM scorecards
                    WHERE driver_id = {p} AND centro = {p}
                    ORDER BY fecha_semana ASC, semana ASC""",
                conn, params=(driver_id, centro)
            )
        return df
    except Exception as _e:
        _log.warning(f"cached_driver_trend error: {_e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def cached_executive_summary(_db_config_key: str, db_config: dict) -> pd.DataFrame:
    """
    Resumen ejecutivo — 2 queries en vez de N×3.

    Query 1: para cada centro, la semana más reciente + todas sus métricas agregadas.
    Query 2: semana anterior por centro para calcular delta WoW.
    """
    try:
        with scorecard.db_connection(db_config) as conn:
            is_pg = db_config['type'] == 'postgresql'

            # ── Query 1: última semana por centro + agregados ──────────────
            # Usamos MAX(timestamp) para determinar qué semana es la "actual"
            # (no MAX(semana) — el usuario puede re-subir semanas pasadas)
            sql_current = """
                WITH ranked AS (
                    SELECT centro, semana,
                           MAX(timestamp) AS last_ts,
                           ROW_NUMBER() OVER (
                               PARTITION BY centro ORDER BY MAX(timestamp) DESC
                           ) AS rn
                    FROM scorecards
                    GROUP BY centro, semana
                ),
                latest AS (SELECT centro, semana FROM ranked WHERE rn = 1)
                SELECT s.centro, s.semana,
                       AVG(s.score)           AS score_medio,
                       AVG(s.dnr)             AS dnr_medio,
                       AVG(s.dcr)  * 100      AS dcr_medio,
                       AVG(s.pod)  * 100      AS pod_medio,
                       SUM(CASE WHEN s.calificacion = '💎 FANTASTIC' THEN 1 ELSE 0 END) AS n_fantastic,
                       SUM(CASE WHEN s.calificacion = '🥇 GREAT'     THEN 1 ELSE 0 END) AS n_great,
                       SUM(CASE WHEN s.calificacion = '⚠️ FAIR'      THEN 1 ELSE 0 END) AS n_fair,
                       SUM(CASE WHEN s.calificacion = '🛑 POOR'      THEN 1 ELSE 0 END) AS n_poor,
                       COUNT(*) AS total
                FROM scorecards s
                JOIN latest l ON s.centro = l.centro AND s.semana = l.semana
                GROUP BY s.centro, s.semana
            """
            df_cur = pd.read_sql_query(sql_current, conn)
            if df_cur.empty:
                return pd.DataFrame()

            # ── Query 2: semana anterior por centro para delta WoW ─────────
            sql_prev = """
                WITH ranked AS (
                    SELECT centro, semana,
                           MAX(timestamp) AS last_ts,
                           ROW_NUMBER() OVER (
                               PARTITION BY centro ORDER BY MAX(timestamp) DESC
                           ) AS rn
                    FROM scorecards
                    GROUP BY centro, semana
                ),
                second AS (SELECT centro, semana FROM ranked WHERE rn = 2)
                SELECT s.centro, AVG(s.score) AS score_prev
                FROM scorecards s
                JOIN second p ON s.centro = p.centro AND s.semana = p.semana
                GROUP BY s.centro
            """
            # Window functions: PostgreSQL soporta nativamente.
            # SQLite >= 3.25 también. Si falla, caemos a prev_score = None.
            try:
                df_prev = pd.read_sql_query(sql_prev, conn)
            except Exception:
                df_prev = pd.DataFrame(columns=['centro', 'score_prev'])

        # ── Merge y cálculo de columnas derivadas ─────────────────────────
        df = df_cur.merge(df_prev, on='centro', how='left')

        df['score_medio']  = df['score_medio'].round(1)
        df['score_prev']   = df['score_prev'].round(1) if 'score_prev' in df.columns else None
        df['dnr_medio']    = df['dnr_medio'].round(2)
        df['dcr_medio']    = df['dcr_medio'].round(2)
        df['pod_medio']    = df['pod_medio'].round(2)
        df['n_fantastic']  = df['n_fantastic'].astype(int)
        df['n_great']      = df['n_great'].astype(int)
        df['n_fair']       = df['n_fair'].astype(int)
        df['n_poor']       = df['n_poor'].astype(int)
        df['total']        = df['total'].astype(int)
        df['pct_top2']     = ((df['n_fantastic'] + df['n_great']) / df['total'] * 100).round(1)

        return df.sort_values('score_medio', ascending=False).reset_index(drop=True)

    except Exception as e:
        _log.warning(f"cached_executive_summary error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def cached_center_targets(_db_config_key: str, db_config: dict, centro: str) -> dict:
    """Targets de un centro — caché 10 min (cambian muy poco)."""
    return scorecard.get_center_targets(centro, db_config=db_config)


@st.cache_data(ttl=300, show_spinner=False)
def cached_centro_tendencia(_db_config_key: str, db_config: dict, centro: str) -> pd.DataFrame:
    """
    Evolución semanal de un centro: % por calificación, score medio, dnr medio.
    Devuelve una fila por semana ordenada cronológicamente.
    """
    try:
        with scorecard.db_connection(db_config) as conn:
            ph = "%s" if db_config['type'] == 'postgresql' else "?"
            df = pd.read_sql_query(
                f"""SELECT semana,
                       MIN(fecha_semana) AS fecha_semana,
                       AVG(score)  AS score_medio,
                       AVG(dnr)    AS dnr_medio,
                       AVG(dcr)*100 AS dcr_medio,
                       AVG(pod)*100 AS pod_medio,
                       COUNT(*)    AS total,
                       SUM(CASE WHEN calificacion='💎 FANTASTIC' THEN 1 ELSE 0 END) AS n_fantastic,
                       SUM(CASE WHEN calificacion='🥇 GREAT'     THEN 1 ELSE 0 END) AS n_great,
                       SUM(CASE WHEN calificacion='⚠️ FAIR'      THEN 1 ELSE 0 END) AS n_fair,
                       SUM(CASE WHEN calificacion='🛑 POOR'      THEN 1 ELSE 0 END) AS n_poor
                   FROM scorecards WHERE centro = {ph}
                   GROUP BY semana ORDER BY MIN(fecha_semana) ASC, semana ASC""",
                conn, params=(centro,)
            )
        if df.empty:
            return df
        total_col = df['total'].replace(0, 1)  # evitar /0
        df['pct_fantastic'] = (df['n_fantastic'] / total_col * 100).round(1)
        df['pct_great']     = (df['n_great']     / total_col * 100).round(1)
        df['pct_fair']      = (df['n_fair']       / total_col * 100).round(1)
        df['pct_poor']      = (df['n_poor']       / total_col * 100).round(1)
        return df
    except Exception as e:
        _log.warning(f"cached_centro_tendencia error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def _cached_sidebar_stats(_db_config_key: str, db_config: dict):
    """Stats rapidas del sidebar, cache 60s."""
    try:
        with scorecard.db_connection(db_config) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM scorecards")
            n_rec = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT semana) FROM scorecards")
            n_weeks = cursor.fetchone()[0]
            cursor.execute(
                "SELECT semana, MAX(timestamp) as t FROM scorecards "
                "GROUP BY semana ORDER BY t DESC LIMIT 1"
            )
            latest = cursor.fetchone()
        return n_rec, n_weeks, latest
    except Exception:
        return 0, 0, None


@st.cache_data(ttl=120, show_spinner=False)
def cached_user_centro(_db_config_key: str, db_config: dict, username: str) -> str | None:
    """Centro asignado a un JT. None = sin restricción."""
    return scorecard.get_user_centro(username, db_config)




@st.cache_data(ttl=300, show_spinner=False)
def cached_prev_week(_db_config_key: str, db_config: dict, centro: str, semana: str) -> pd.DataFrame:
    """
    Scorecard de la semana anterior a `semana` para un centro — caché 5 min.
    Evita una query raw sin caché en cada re-render del tab Scorecard.
    """
    try:
        p = "%s" if db_config['type'] == 'postgresql' else "?"
        with scorecard.db_connection(db_config) as conn:
            df_meta = pd.read_sql_query(
                f"SELECT semana FROM scorecards "
                f"WHERE centro = {p} "
                f"AND fecha_semana < (SELECT MIN(fecha_semana) FROM scorecards "
                f"                    WHERE centro = {p} AND semana = {p}) "
                f"GROUP BY semana ORDER BY MAX(fecha_semana) DESC LIMIT 1",
                conn, params=(centro, centro, semana)
            )
        if df_meta.empty:
            return pd.DataFrame()
        prev_week = df_meta['semana'].iloc[0]
        return cached_scorecard(_db_config_key, db_config, prev_week, centro)
    except Exception as _e:
        _log.warning(f"cached_prev_week error: {_e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def cached_trend_batch(_db_config_key: str, db_config: dict, centro: str,
                       n_weeks: int = 4) -> pd.DataFrame:
    """
    Pre-carga las últimas `n_weeks` semanas de tendencia para todos los
    conductores de un centro — caché 5 min.
    Evita 2 queries raw en cada re-render del tab Scorecard.
    """
    try:
        p = "%s" if db_config['type'] == 'postgresql' else "?"
        with scorecard.db_connection(db_config) as conn:
            df_semanas = pd.read_sql_query(
                f"SELECT DISTINCT semana FROM scorecards WHERE centro = {p} "
                f"ORDER BY semana DESC LIMIT {n_weeks}",
                conn, params=(centro,)
            )
            if df_semanas.empty:
                return pd.DataFrame()
            semanas = df_semanas['semana'].tolist()
            ph_list = ', '.join([p] * len(semanas))
            return pd.read_sql_query(
                f"SELECT driver_id, semana, score, calificacion "
                f"FROM scorecards WHERE centro = {p} "
                f"AND semana IN ({ph_list}) "
                f"ORDER BY fecha_semana ASC, semana ASC",
                conn, params=([centro] + semanas)
            )
    except Exception as _e:
        _log.warning(f"cached_trend_batch error: {_e}")
        return pd.DataFrame()

def db_config_key(db_config: dict) -> str:
    """Clave estable para usar en el caché (evita pasar dicts como arg de caché)."""
    return f"{db_config.get('type')}:{db_config.get('host','local')}:{db_config.get('database','')}"


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: limpiar todas las cachés en un único lugar
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE DISPLAY — nivel módulo (antes redefinidas en cada render)
# ─────────────────────────────────────────────────────────────────────────────

def _score_color(s) -> str:
    """Color hex según score."""
    if s >= SCORE_FANTASTIC: return '#0d6efd'
    elif s >= SCORE_GREAT:     return '#198754'
    elif s >= SCORE_FAIR:       return '#fd7e14'
    else:                       return '#dc3545'


def _fmt_pct(val, decimals=2) -> str:
    """Formatea un valor 0-1 como porcentaje."""
    try:
        return f"{float(val)*100:.{decimals}f}%" if val is not None and str(val) not in ('nan','None','') else "—"
    except Exception:
        return "—"


def _fmt_num(val, entero=True) -> str:
    """Formatea un número."""
    try:
        if val is None or str(val) in ('nan','None',''):
            return "—"
        return str(int(round(float(val)))) if entero else f"{float(val):.2f}"
    except Exception:
        return "—"


def _diff_badge(csv_val, pdf_val, is_pct=True) -> str:
    """Badge de diferencia CSV → PDF."""
    try:
        a, b = float(csv_val), float(pdf_val)
        diff = (b - a) * (100 if is_pct else 1)
        sign = '+' if diff >= 0 else ''
        unit = 'pp' if is_pct else ''
        txt  = f"{sign}{diff:.2f}{unit}"
        if abs(diff) < (0.05 if is_pct else 1):
            return f"<span style='color:#198754;font-weight:700'>✅ {txt}</span>"
        elif abs(diff) < (0.5 if is_pct else 5):
            return f"<span style='color:#fd7e14;font-weight:700'>🟡 {txt}</span>"
        else:
            return f"<span style='color:#dc3545;font-weight:700'>🔴 {txt}</span>"
    except Exception:
        return "—"


def _metric_row(label, value_raw, target, higher_is_better=True,
                is_pct=True, is_int=False) -> str:
    """Fila visual con barra de progreso y color vs target."""
    if value_raw is None or str(value_raw) in ('nan','None',''):
        return (f"<tr><td style='padding:6px 8px;color:#6c757d;"
                f"font-size:0.83em;font-weight:600'>{label}</td>"
                f"<td colspan='2' style='padding:6px 8px;color:#6c757d'>—</td></tr>")
    try:
        v = float(value_raw)
    except Exception:
        return ""

    if is_int:
        disp = str(int(round(v)))
    elif is_pct:
        disp = f"{v*100:.2f}%"
    else:
        disp = f"{v:.2f}"

    if target is not None:
        ok = (v >= target) if higher_is_better else (v <= target)
        status_color = '#198754' if ok else '#dc3545'
        status_icon  = '✅' if ok else '⚠️'
        if is_pct:
            bar_pct = min(100, v * 100)
        else:
            bar_pct = min(100, max(0, 100 - (v / max(target, 1)) * 100)) if not higher_is_better else min(100, v)
        bar_html = (
            f"<div style='background:#2d3748;border-radius:4px;"
            f"height:6px;width:100%;margin-top:3px;position:relative'>"
            f"<div style='background:{status_color};width:{bar_pct:.0f}%;"
            f"height:6px;border-radius:4px'></div>"
            f"</div>"
        )
    else:
        status_color = '#6c757d'
        status_icon  = ''
        bar_html = ''

    return (
        f"<tr>"
        f"<td style='padding:5px 8px;color:#adb5bd;font-size:0.82em;"
        f"font-weight:600;width:40%'>{label}</td>"
        f"<td style='padding:5px 8px;font-weight:800;color:{status_color};"
        f"font-size:0.95em;text-align:right'>{disp}</td>"
        f"<td style='padding:5px 8px;font-size:0.9em'>{status_icon}"
        f"{bar_html}</td>"
        f"</tr>"
    )


def _get_mini_trend(driver_id: str, df_trend_batch: "pd.DataFrame") -> str:
    """Devuelve HTML con los últimos scores del DA como bolitas de color."""
    if df_trend_batch.empty:
        return ""
    rows = df_trend_batch[df_trend_batch['driver_id'] == driver_id].tail(6)
    if rows.empty:
        return ""
    dots = []
    for r in rows.itertuples(index=False):
        c = CALIFICACION_COLORS.get(str(r.calificacion), '#6c757d')
        dots.append(
            f"<span title='{r.semana}: {int(r.score)}' "
            f"style='display:inline-block;width:22px;height:22px;"
            f"border-radius:50%;background:{c};color:white;"
            f"font-size:0.6em;font-weight:700;text-align:center;"
            f"line-height:22px;margin:0 1px'>{int(r.score)}</span>"
        )
    return "<span style='display:inline-flex;align-items:center;gap:1px'>" + "".join(dots) + "</span>"


def _is_still_locked(val, now_dt) -> bool:
    """Comprueba si una cuenta sigue bloqueada."""
    if val is None:
        return False
    try:
        return datetime.strptime(str(val)[:19], "%Y-%m-%d %H:%M:%S") > now_dt
    except Exception:
        return False



def _render_pagination(page_key: str, page: int, total_pages: int,
                       total_rows: int, page_size: int,
                       prev_key: str = None, next_key: str = None) -> int:
    """
    Renderiza controles de paginación reutilizables.
    Devuelve la página actual (puede haber cambiado).
    """
    if total_pages <= 1:
        return page

    if prev_key is None:
        prev_key = f"pag_prev_{page_key}"
    if next_key is None:
        next_key = f"pag_next_{page_key}"

    offset = page * page_size
    nav = st.columns([1, 3, 1])
    with nav[0]:
        if st.button("◀ Anterior", key=prev_key,
                     disabled=(page == 0), use_container_width=True):
            st.session_state[page_key] = page - 1
            st.rerun()
    with nav[1]:
        st.markdown(
            f"<div style='text-align:center;padding:0.4rem 0;"
            f"color:#6c757d;font-size:0.9em'>"
            f"Página {page+1} de {total_pages} "
            f"({offset+1}–{min(offset+page_size, total_rows)} de {total_rows})"
            f"</div>",
            unsafe_allow_html=True
        )
    with nav[2]:
        if st.button("Siguiente ▶", key=next_key,
                     disabled=(page >= total_pages - 1), use_container_width=True):
            st.session_state[page_key] = page + 1
            st.rerun()
    return st.session_state.get(page_key, page)

def _clear_all_caches():
    """Invalida todas las cachés de datos. Llamar tras cualquier escritura en BD."""
    for _fn in [
        cached_scorecard, cached_available_batches, get_active_weeks,
        cached_executive_summary, cached_driver_trend, cached_meta,
        cached_centro_tendencia, cached_center_targets, cached_user_centro,
        cached_prev_week, cached_trend_batch, _cached_sidebar_stats,
    ]:
        try:
            _fn.clear()
        except Exception:
            pass



def _get_user_credentials(username: str, db_config: dict) -> tuple:
    """Un solo round-trip: devuelve (pw_hash | None, user_dict | None)."""
    try:
        ph = '%s' if db_config.get('type') == 'postgresql' else '?'
        with scorecard.db_connection(db_config) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT password, username, role, must_change_password, centro_asignado "
                f"FROM users WHERE LOWER(username) = {ph} AND active = 1",
                (username.strip().lower(),)
            )
            row = cursor.fetchone()
        if not row:
            return None, None
        user_dict = {
            "name": row[1], "role": row[2],
            "must_change_password": bool(row[3]), "centro_asignado": row[4]
        }
        return row[0], user_dict
    except Exception as e:
        _log.warning(f"_get_user_credentials error: {e}")
        return None, None


def get_user_password_hash(username: str, db_config: dict) -> str | None:
    """Obtiene el hash de contraseña de un usuario. Devuelve None si no existe."""
    pw_hash, _ = _get_user_credentials(username, db_config)
    return pw_hash


def get_user_data(username: str, db_config: dict) -> dict | None:
    """Obtiene username, role y must_change_password de un usuario activo."""
    _, user_dict = _get_user_credentials(username, db_config)
    return user_dict


def update_user_password(username: str, new_hash: str, db_config: dict) -> bool:
    """Wrapper → scorecard.update_user_password (definida en motor.py para testabilidad)."""
    return scorecard.update_user_password(username, new_hash, db_config)


def get_user_role(username: str, db_config: dict) -> str | None:
    """Devuelve el rol de un usuario o None si no existe."""
    try:
        with scorecard.db_connection(db_config) as conn:
            cursor = conn.cursor()
            q = ("SELECT role FROM users WHERE LOWER(username) = %s AND active = 1"
                 if db_config['type'] == 'postgresql' else
                 "SELECT role FROM users WHERE LOWER(username) = ? AND active = 1")
            cursor.execute(q, (username.strip().lower(),))
            row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        _log.warning(f"get_user_role error: {e}")
        return None


# ── Renderers HTML ─────────────────────────────────────────────────────────────

CALIFICACION_COLORS = {
    '💎 FANTASTIC': '#0d6efd',
    '🥇 GREAT':     '#198754',
    '⚠️ FAIR':      '#fd7e14',
    '🛑 POOR':      '#dc3545',
}

# Umbrales de score — fuente única de verdad para colores y gráficos
SCORE_FANTASTIC = 90
SCORE_GREAT     = 80
SCORE_FAIR      = 60
# < SCORE_FAIR → POOR → dc3545

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






def check_login() -> bool:
    if "user" not in st.session_state:
        st.markdown("""
        <div style='text-align:center;padding:3rem 0 1rem'>
            <div style='font-size:3rem'>🛡️</div>
            <h1 style='margin:0.5rem 0'>Winiw Quality Scorecard</h1>
            <p style='color:#6c757d'>Amazon DSP · Calidad</p>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1, 1.5, 1])
        with c2:
            with st.form("login_form"):
                username = st.text_input("👤 Usuario", max_chars=100)
                password = st.text_input("🔒 Contraseña", type="password", max_chars=128)
                submitted = st.form_submit_button("Iniciar Sesión", use_container_width=True, type="primary")

                if submitted:
                    try:
                        uname = username.strip().lower()

                        # ── Comprobar si está bloqueado (BD persistente) ────
                        locked, remaining = scorecard.check_login_locked(uname, db_config)
                        if locked:
                            mins = remaining // 60
                            secs = remaining % 60
                            st.error(
                                f"🔒 Cuenta temporalmente bloqueada por demasiados intentos fallidos. "
                                f"Inténtalo de nuevo en **{mins}m {secs}s**."
                            )
                            _log.warning(f"[RATE LIMIT] Intento bloqueado para '{uname}' ({remaining}s restantes)")
                            return False

                        # ── Verificar credenciales (1 sola query DB) ───────
                        pw_hash, user_info = _get_user_credentials(uname, db_config)
                        if pw_hash and scorecard.verify_password(password, pw_hash):
                            scorecard.record_login_attempt(uname, success=True, db_config=db_config)
                            st.session_state["user"] = user_info
                            st.session_state["last_activity"] = datetime.now()
                            st.session_state["login_time"] = datetime.now()
                            if user_info and user_info.get("must_change_password"):
                                st.session_state["force_change_pw"] = True
                            _audit(f"Login exitoso ({user_info['role']})")
                            st.rerun()
                        else:
                            scorecard.record_login_attempt(
                                uname, success=False, db_config=db_config,
                                max_attempts=MAX_LOGIN_ATTEMPTS,
                                lockout_minutes=LOGIN_LOCKOUT_MINUTES,
                            )
                            # Comprobar si acaba de quedar bloqueado tras este intento
                            now_locked, _ = scorecard.check_login_locked(uname, db_config)
                            _audit(f"Login fallido para '{uname}'")

                            if now_locked:
                                st.error(
                                    f"🔒 Demasiados intentos fallidos. "
                                    f"Cuenta bloqueada durante **{LOGIN_LOCKOUT_MINUTES} minutos**."
                                )
                            else:
                                st.error("❌ Usuario o contraseña incorrectos.")
                    except Exception as e:
                        st.error(f"❌ Error de conexión: {e}")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# INICIALIZACIÓN DE BASE DE DATOS — una sola vez por proceso
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def _init_app() -> dict:
    """
    Ejecutado UNA SOLA VEZ por proceso (no en cada re-render).
    Inicializa la BD y devuelve la config para que el resto de la app la use.
    """
    cfg = get_db_config()
    scorecard.init_database(cfg)
    return cfg

db_config = _init_app()
_DB_KEY   = db_config_key(db_config)

if not check_login():
    st.stop()

check_session_timeout()

# ── Forzar cambio de contraseña (primer acceso o reset por admin) ─────────────
if st.session_state.get("force_change_pw"):
    st.warning("🔐 **Debes cambiar tu contraseña antes de continuar.**")
    with st.form("force_pw_form"):
        new_pw_f  = st.text_input("Nueva contraseña (mínimo 8 caracteres)", type="password")
        conf_pw_f = st.text_input("Confirmar contraseña", type="password")
        submitted = st.form_submit_button("💾 Guardar y continuar", type="primary", use_container_width=True)
        if submitted:
            if len(new_pw_f) < 8:
                st.error("❌ La contraseña debe tener al menos 8 caracteres.")
            elif new_pw_f != conf_pw_f:
                st.error("❌ Las contraseñas no coinciden.")
            else:
                _uname_f = st.session_state["user"]["name"]
                new_hash = scorecard.hash_password(new_pw_f)
                if update_user_password(_uname_f, new_hash, db_config):
                    st.session_state.pop("force_change_pw", None)
                    _audit("Cambió contraseña obligatoria")
                    st.success("✅ Contraseña actualizada. Accediendo...")
                    st.rerun()
                else:
                    st.error("❌ Error al guardar la contraseña. Contacta con un administrador.")
    st.stop()

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

# Centro asignado al JT (None = sin restricción — ve todos los centros)
JT_CENTRO = (
    cached_user_centro(_DB_KEY, db_config, user_data_session['name'])
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
        try:
            n_rec, n_weeks, latest = _cached_sidebar_stats(_DB_KEY, db_config)
            st.metric("Registros totales", f"{n_rec:,}")
            st.metric("Semanas en BD", n_weeks)
            if latest:
                st.success(f"Semana activa: **{latest[0]}**")
        except Exception:
            st.warning("BD no disponible")
        # Aviso de seguridad si bcrypt no está disponible
        if not scorecard.HAS_BCRYPT:
            st.warning("⚠️ **bcrypt no instalado** — contraseñas protegidas con SHA-256 (menos seguro). "
                       "Ejecuta `pip install bcrypt` para activar el hash seguro.")

    if is_jt and ALLOWED_WEEKS_JT:
        st.divider()
        semana_actual = ALLOWED_WEEKS_JT[0]
        semana_prev   = ALLOWED_WEEKS_JT[1] if len(ALLOWED_WEEKS_JT) > 1 else "—"
        st.markdown(f"""
        <div style='font-size:0.85em;color:#6c757d'>
        📅 <b>Semana en curso:</b> {semana_actual}<br>
        📅 <b>Semana anterior:</b> {semana_prev}<br>
        🏢 <b>Centro:</b> {JT_CENTRO if JT_CENTRO else "Todos"}
        </div>
        """, unsafe_allow_html=True)

    if is_admin:
        st.divider()
        with st.expander("🔧 Override Manual"):
            center_manual = st.text_input("Centro", "", help="Sobrescribir centro detectado")
            _wm_raw       = st.text_input("Semana", "", placeholder="ej: W07")
            # Normalizar W5 → W05, W9 → W09
            if _wm_raw and _wm_raw.upper().startswith("W"):
                try:
                    week_manual = f"W{int(_wm_raw[1:]):02d}"
                except ValueError:
                    week_manual = _wm_raw
            else:
                week_manual = _wm_raw
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
        <p style='margin:0;color:#6c757d;font-size:0.9em'>Amazon DSP</p>
    </div>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

if is_admin:
    tabs = st.tabs(["🏢 Dashboard", "📤 Subir Archivos", "📋 Subir PDFs", "📊 Ver Conductores", "📈 Histórico", "👤 Perfil", "👑 Admin"])
    tab_dash, tab_proc, tab_dsp, tab_excel, tab_hist, tab_profile, tab_admin = tabs
else:
    tabs = st.tabs(["📊 Ver Conductores", "📈 Histórico", "👤 Perfil"])
    tab_excel, tab_hist, tab_profile = tabs
    tab_dash = tab_proc = tab_dsp = tab_admin = None

# ─────────────────────────────────────────────────────────────────────────────
# TAB: DASHBOARD EJECUTIVO (solo admins)
# ─────────────────────────────────────────────────────────────────────────────

if tab_dash:
    with tab_dash:
        st.header("📊 Resumen de Centros")

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
                        <div style='font-size:2em;font-weight:800;color:#0d6efd'>{total_fantastic}</div>
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
            st.caption(
                "Puntuación de 0 a 100 calculada por conductor. Parte de 100 y descuenta según incidencias: "
                "DNR (hasta -70 pts), DCR bajo (hasta -40), POD bajo (hasta -25), CDF bajo (-15), "
                "RTS alto (-15), CC bajo (-10), FDPS bajo (-10). "
                "**💎 FANTASTIC** ≥90 · **🥇 GREAT** ≥80 · **⚠️ FAIR** ≥60 · **🛑 POOR** <60. "
                "El score del centro es la media de todos sus conductores esa semana."
            )

            rank_cols = st.columns(min(n_centros, 4))
            for i, row in enumerate(df_exec.itertuples(index=False)):
                col = rank_cols[i % len(rank_cols)]
                delta_score = None
                if row.score_prev is not None:
                    delta_score = round(row.score_medio - row.score_prev, 1)

                medal = {0: '🥇', 1: '🥈', 2: '🥉'}.get(i, f"#{i+1}")
                score_color = (
                    _score_color(row.score_medio)
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
                    <div style='font-size:1.1em;font-weight:800;color:{score_color}'>{row.centro}</div>
                    <div style='font-size:0.8em;color:#6c757d'>{row.semana}</div>
                    <div style='font-size:2.5em;font-weight:900;color:{score_color};line-height:1.1'>{row.score_medio}</div>
                    <div>{delta_html}</div>
                    <hr style='margin:0.5rem 0;border-color:{score_color}30'>
                    <div style='font-size:0.8em;color:#6c757d'>{row.total} conductores</div>
                    <div style='font-size:0.8em'>
                        <span style='color:#0d6efd'>💎{row.n_fantastic}</span> &nbsp;
                        <span style='color:#198754'>🥇{row.n_great}</span> &nbsp;
                        <span style='color:#fd7e14'>⚠️{row.n_fair}</span> &nbsp;
                        <span style='color:#dc3545'>🛑{row.n_poor}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")

            # ── Tabla comparativa detallada ────────────────────────────────
            st.subheader("📊 Métricas Comparativas")
            st.caption("Última semana disponible por centro. DCR = tasa de entregas completadas, POD = foto de entrega, FANTASTIC+GREAT = % de conductores en las dos mejores categorías.")

            rows_html = []
            for i, row in enumerate(df_exec.itertuples(index=False)):
                bg = '#1e2530' if i % 2 == 0 else '#262d3a'
                score_c = (
                    _score_color(row.score_medio)
                )
                delta_score = None
                if row.score_prev is not None:
                    try:
                        diff = round(float(row.score_medio) - float(row.score_prev), 1)
                        if not (diff != diff):  # NaN check
                            delta_score = diff
                    except (TypeError, ValueError):
                        pass

                delta_cell = '<span style="color:#6c757d">—</span>'
                if delta_score is not None:
                    dc = '#198754' if delta_score >= 0 else '#dc3545'
                    di = '▲' if delta_score > 0 else ('▼' if delta_score < 0 else '→')
                    delta_cell = f'<span style="color:{dc}">{di} {delta_score:+.1f}</span>'

                # Barra de % top2
                pct_bar = f"""<div style='display:flex;align-items:center;gap:6px'>
                    <div style='flex:1;background:#e9ecef;border-radius:3px;height:6px'>
                    <div style='width:{row.pct_top2}%;background:{score_c};height:6px;border-radius:3px'></div></div>
                    <span style='font-size:0.85em;font-weight:700;color:{score_c}'>{row.pct_top2}%</span></div>"""

                rows_html.append(f"""
                <tr style='background:{bg}'>
                    <td style='padding:8px 10px;font-weight:700'>{row.centro}</td>
                    <td style='padding:8px 10px;color:#6c757d'>{row.semana}</td>
                    <td style='padding:8px 10px;font-weight:800;color:{score_c};font-size:1.1em'>{row.score_medio}</td>
                    <td style='padding:8px 10px'>{delta_cell}</td>
                    <td style='padding:8px 10px;text-align:center'><b style='color:{"#dc3545" if row.dnr_medio>=2 else "#198754"}'>{row.dnr_medio:.2f}</b></td>
                    <td style='padding:8px 10px;text-align:center'>{row.dcr_medio:.2f}%</td>
                    <td style='padding:8px 10px;text-align:center'>{row.pod_medio:.2f}%</td>
                    <td style='padding:8px 10px'>{pct_bar}</td>
                    <td style='padding:8px 10px;text-align:center;color:#dc3545;font-weight:700'>{row.n_poor}</td>
                    <td style='padding:8px 10px;text-align:center;color:#6c757d'>{row.total}</td>
                </tr>
                """)

            st.html(f"""
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
            """)

            st.markdown("---")

            # ── Gráfico de barras: Score por centro ────────────────────────
            st.subheader("📈 Score Medio por Centro")
            st.caption("Media del score de todos los conductores activos por centro en la última semana disponible. Verde = GREAT/FANTASTIC (≥80), Naranja = FAIR (60-79), Rojo = POOR (<60).")
            df_chart = df_exec[['centro', 'score_medio']].fillna(0).copy()
            df_chart['score_medio'] = df_chart['score_medio'].astype(float)
            if not df_chart.empty:
                _y_min = max(0, float(df_chart['score_medio'].min()) - 12)
                _y_max = min(105, float(df_chart['score_medio'].max()) + 15)
                df_chart['label'] = df_chart['score_medio'].apply(lambda x: f"{x:.1f}")
                df_chart['tier'] = pd.cut(
                    df_chart['score_medio'],
                    bins=[-1, SCORE_FAIR, SCORE_GREAT, SCORE_FANTASTIC, 101],
                    labels=['Poor', 'Fair', 'Great', 'Fantastic']
                ).astype(str)
                _color_scale = alt.Scale(
                    domain=['Fantastic', 'Great', 'Fair', 'Poor'],
                    range=['#0d6efd', '#198754', '#fd7e14', '#dc3545']
                )
                # Ordenar igual que la tabla: score descendente
                _sort_order = df_chart.sort_values('score_medio', ascending=False)['centro'].tolist()
                _bar_size = min(60, max(20, 400 // max(1, len(df_chart))))
                _bars = (alt.Chart(df_chart)
                    .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, size=_bar_size)
                    .encode(
                        x=alt.X('centro:N',
                                sort=_sort_order,
                                axis=alt.Axis(labelAngle=0, labelColor='white',
                                              labelFontSize=13, labelFontWeight='bold',
                                              titleColor='white', tickColor='white'),
                                title='Centro'),
                        y=alt.Y('score_medio:Q', scale=alt.Scale(domain=[_y_min, _y_max]),
                                axis=alt.Axis(labelColor='white', titleColor='white'),
                                title='Score'),
                        color=alt.Color('tier:N', scale=_color_scale, legend=None),
                        tooltip=[alt.Tooltip('centro:N', title='Centro'),
                                 alt.Tooltip('score_medio:Q', title='Score', format='.1f'),
                                 alt.Tooltip('tier:N', title='Nivel')]
                    ).properties(height=230))
                _text_score = (alt.Chart(df_chart)
                    .mark_text(dy=-10, fontSize=13, fontWeight='bold', color='white')
                    .encode(x=alt.X('centro:N', sort=_sort_order),
                            y=alt.Y('score_medio:Q', scale=alt.Scale(domain=[_y_min, _y_max])),
                            text=alt.Text('label:N')))
                st.altair_chart(_bars + _text_score, use_container_width=True)

            # ── Distribución global POOR ───────────────────────────────────
            if df_exec['n_poor'].sum() > 0:
                st.markdown("---")
                st.subheader("🚨 Conductores POOR por Centro")
                df_poor_chart = df_exec[df_exec['n_poor'] > 0][['centro', 'n_poor']].copy()
                if not df_poor_chart.empty:
                    df_poor_chart['label'] = df_poor_chart['n_poor'].astype(str)
                    _top_poor = int(df_poor_chart['n_poor'].max()) + 3
                    _bars_p = (alt.Chart(df_poor_chart)
                        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, color='#dc3545', size=min(80, max(20, 500 // max(1, len(df_poor_chart)))))
                        .encode(
                            x=alt.X('centro:N',
                                    axis=alt.Axis(labelAngle=0, labelColor='white',
                                                  labelFontSize=13, labelFontWeight='bold',
                                                  titleColor='white', tickColor='white'),
                                    title='Centro'),
                            y=alt.Y('n_poor:Q', title='Nº POOR',
                                    scale=alt.Scale(domain=[0, _top_poor]),
                                    axis=alt.Axis(format='d', labelColor='white', titleColor='white')),
                            tooltip=[alt.Tooltip('centro:N', title='Centro'),
                                     alt.Tooltip('n_poor:Q', title='POOR')]
                        ).properties(height=230))
                    _text_p = (alt.Chart(df_poor_chart)
                        .mark_text(dy=-8, fontSize=14, fontWeight='bold', color='white')
                        .encode(x=alt.X('centro:N'),
                                y=alt.Y('n_poor:Q', scale=alt.Scale(domain=[0, _top_poor])),
                                text=alt.Text('label:N')))
                    st.altair_chart(_bars_p + _text_p, use_container_width=True)

            # ── G) Tendencia semanal por centro ───────────────────────────
            st.markdown("---")
            st.subheader("📉 Tendencia Semanal por Centro")
            st.caption("Evolución semana a semana del score medio y DNR de cada centro. Se necesitan al menos 2 semanas de datos para mostrar el gráfico.")

            centros_trend = sorted(df_exec['centro'].tolist())
            sel_trend_centro = st.selectbox("Seleccionar centro", centros_trend,
                                            key="trend_centro_dashboard")

            df_trend_c = cached_centro_tendencia(_DB_KEY, db_config, sel_trend_centro)

            if df_trend_c.empty or len(df_trend_c) < 2:
                st.info("Se necesitan al menos 2 semanas de datos para mostrar la tendencia.")
            else:
                tc1, tc2 = st.columns(2)
                with tc1:
                    st.markdown("**Score medio**")
                    _df_score = df_trend_c[['semana', 'score_medio']].copy()
                    _df_score['score_medio'] = pd.to_numeric(_df_score['score_medio'], errors='coerce').fillna(0.0)
                    _s_min = max(0, float(_df_score['score_medio'].min()) - 10)
                    _s_max = min(100, float(_df_score['score_medio'].max()) + 10)
                    st.altair_chart(
                        alt.Chart(_df_score)
                        .mark_line(point=True, strokeWidth=3, color='#0d6efd')
                        .encode(
                            x=alt.X('semana:N', title='Semana'),
                            y=alt.Y('score_medio:Q', scale=alt.Scale(domain=[_s_min, _s_max]),
                                    title='Score'),
                            tooltip=[alt.Tooltip('semana:N'), alt.Tooltip('score_medio:Q', format='.1f')]
                        ).properties(height=220),
                        use_container_width=True
                    )
                with tc2:
                    st.markdown("**DNR medio**")
                    _df_dnr = df_trend_c[['semana', 'dnr_medio']].copy()
                    _df_dnr['dnr_medio'] = pd.to_numeric(_df_dnr['dnr_medio'], errors='coerce').fillna(0.0)
                    _d_max = max(1.0, float(_df_dnr['dnr_medio'].max()) * 1.3)
                    st.altair_chart(
                        alt.Chart(_df_dnr)
                        .mark_line(point=True, strokeWidth=3, color='#dc3545')
                        .encode(
                            x=alt.X('semana:N', title='Semana'),
                            y=alt.Y('dnr_medio:Q', scale=alt.Scale(domain=[0, _d_max]),
                                    title='DNR'),
                            tooltip=[alt.Tooltip('semana:N'), alt.Tooltip('dnr_medio:Q', format='.2f')]
                        ).properties(height=220),
                        use_container_width=True
                    )

                # Distribución apilada en tabla visual
                st.markdown("**Distribución de calificaciones por semana (%)**")
                df_dist = df_trend_c[['semana','pct_fantastic','pct_great','pct_fair','pct_poor']].copy()
                df_dist.columns = ['Semana','💎 FANTASTIC','🥇 GREAT','⚠️ FAIR','🛑 POOR']

                rows_dist = []
                for _, r in df_dist.iterrows():
                    bar_html = ""
                    for col, color in [('💎 FANTASTIC','#0d6efd'),('🥇 GREAT','#198754'),
                                       ('⚠️ FAIR','#fd7e14'),('🛑 POOR','#dc3545')]:
                        w = max(0, min(100, r[col]))
                        if w > 0:
                            bar_html += (f"<div style='display:inline-block;width:{w}%;height:18px;"
                                         f"background:{color};vertical-align:middle' "
                                         f"title='{col}: {w:.1f}%'></div>")
                    rows_dist.append(
                        f"<tr><td style='padding:6px 10px;font-weight:600'>{r['Semana']}</td>"
                        f"<td style='padding:6px 10px'>{r['💎 FANTASTIC']:.1f}%</td>"
                        f"<td style='padding:6px 10px'>{r['🥇 GREAT']:.1f}%</td>"
                        f"<td style='padding:6px 10px'>{r['⚠️ FAIR']:.1f}%</td>"
                        f"<td style='padding:6px 10px;color:#dc3545;font-weight:700'>{r['🛑 POOR']:.1f}%</td>"
                        f"<td style='padding:6px 10px;min-width:160px'>"
                        f"<div style='background:#e9ecef;border-radius:3px;overflow:hidden'>{bar_html}</div>"
                        f"</td></tr>"
                    )

                st.markdown(f"""
                <div style='overflow-x:auto;border-radius:8px;border:1px solid #dee2e6'>
                <table style='width:100%;border-collapse:collapse;font-size:0.88em'>
                    <thead>
                        <tr style='background:#232f3e;color:white'>
                            <th style='padding:8px 10px;text-align:left'>Semana</th>
                            <th style='padding:8px 10px'>💎 FANTAS.</th>
                            <th style='padding:8px 10px'>🥇 GREAT</th>
                            <th style='padding:8px 10px'>⚠️ FAIR</th>
                            <th style='padding:8px 10px'>🛑 POOR</th>
                            <th style='padding:8px 10px;text-align:left'>Distribución</th>
                        </tr>
                    </thead>
                    <tbody>{''.join(rows_dist)}</tbody>
                </table></div>
                """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB: PROCESAMIENTO (solo admins — sin cambios funcionales)
# ─────────────────────────────────────────────────────────────────────────────

if tab_proc:
    with tab_proc:
        st.header("📂 Subir Archivos")

        uploaded_files = st.file_uploader(
            "📁 Arrastra o selecciona archivos",
            accept_multiple_files=True,
            help="Soporta: CSV, XLSX, HTML (Concessions, Quality, False Scan, DWC, FDPS)"
        )

        if uploaded_files:
            batches = {}
            for f in uploaded_files:
                week, center, _year_file = scorecard.extract_info_from_path(f.name)
                bk = (week, center)
                if bk not in batches:
                    batches[bk] = {
                        'concessions': [], 'dsc_concessions': [], 'quality': [], 'false_scan': [],
                        'dwc': [], 'fdps': [], 'daily': [], 'official': [],
                        'files_count': 0,
                        'year': _year_file,
                    }
                elif _year_file and not batches[bk].get('year'):
                    batches[bk]['year'] = _year_file
                name = f.name.lower()
                if re.match(scorecard.Config.PATTERN_DSC_CONCESSIONS, name, re.IGNORECASE):
                    batches[bk]['dsc_concessions'].append(f)
                elif re.match(scorecard.Config.PATTERN_CONCESSIONS, name, re.IGNORECASE):
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
                    curr_t = cached_center_targets(_DB_KEY, db_config, center)
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
                                cached_center_targets.clear()
                                current_week   = week_manual if week_manual else week
                                current_center = center_manual if center_manual else center
                                _year_to_save = data.get('year')
                                if _year_to_save is None:
                                    _year_to_save = datetime.now().year
                                    
                                df = scorecard.process_single_batch(
                                    data['concessions'], data['quality'], data['false_scan'],
                                    data['dwc'], data['fdps'], data['daily'],
                                    path_dsc_concessions=data.get('dsc_concessions') or None,
                                    targets=new_t
                                )
                                if df is not None:
                                    ok, _save_err = scorecard.save_to_database(
                                        df, current_week, current_center,
                                        db_config=db_config,
                                        uploaded_by=user_data_session['name'],
                                        year=_year_to_save,
                                    )
                                    # Invalidar solo el caché relacionado con este lote
                                    # (no borramos todo para no perjudicar a usuarios concurrentes)
                                    _clear_all_caches()
                                    _audit(f"Procesó {current_center} {current_week} — {len(df)} conductores")

                                    if ok:
                                        st.success(f"✅ {len(df)} conductores procesados y guardados.")

                                        # ── H) Alertas automáticas ──────────────────────
                                        try:
                                            smtp_cfg   = dict(st.secrets.get("smtp", {})) if hasattr(st, 'secrets') else {}
                                            alert_mail = st.secrets.get("alert_email", "") if hasattr(st, 'secrets') else ""
                                            if smtp_cfg and alert_mail:
                                                n_alerted = scorecard.check_and_send_alerts(
                                                    current_week, current_center,
                                                    smtp_cfg=smtp_cfg,
                                                    alert_email=alert_mail,
                                                    db_config=db_config
                                                )
                                                if n_alerted > 0:
                                                    st.warning(
                                                        f"⚠️ Alerta enviada: {n_alerted} conductor(es) "
                                                        f"en POOR 2 semanas consecutivas."
                                                    )
                                        except Exception as _ae:
                                            _log.warning(f"Alertas: {_ae}")
                                    else:
                                        st.warning(f"⚠️ Procesado pero error al guardar en BD: `{_save_err}`")

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

        # ── I) Importación histórica masiva (ZIP) ─────────────────────────
        if is_admin:
            st.divider()
            st.subheader("📦 Importación Histórica Masiva")
            st.markdown(
                "Sube un ZIP con carpetas organizadas por semana/centro. "
                "Cada carpeta debe contener los mismos archivos que el procesamiento normal."
            )
            with st.expander("📋 Estructura esperada del ZIP", expanded=False):
                st.code(
                    "historico.zip\n"
                    "├── DIC1_W01/\n"
                    "│   ├── concessions_DIC1_W01.csv\n"
                    "│   ├── quality_overview_DIC1_W01.csv\n"
                    "│   └── false_scan_DIC1_W01.html\n"
                    "├── DIC1_W02/\n"
                    "│   └── ...\n"
                    "└── MAD1_W01/\n"
                    "    └── ...",
                    language="text"
                )

            zip_file = st.file_uploader("📁 Subir ZIP histórico", type=["zip"], key="bulk_zip")

            if zip_file:
                if st.button("🚀 Procesar ZIP completo", type="primary", use_container_width=True):
                    with st.spinner("Procesando archivos del ZIP..."):
                        results_bulk = []
                        errors_bulk  = []

                        with tempfile.TemporaryDirectory() as tmpdir:
                            # Extraer ZIP
                            try:
                                with zipfile.ZipFile(zip_file, 'r') as zf:
                                    zf.extractall(tmpdir)
                            except zipfile.BadZipFile:
                                st.error("❌ El archivo no es un ZIP válido.")
                                st.stop()

                            # Recopilar TODOS los archivos válidos del ZIP (sin importar estructura de carpetas)
                            root = pathlib.Path(tmpdir)
                            all_files = [
                                f for f in root.rglob('*')
                                if f.is_file() and f.suffix.lower() in ['.csv', '.xlsx', '.html', '.xls']
                            ]

                            # Agrupar por (centro, semana) detectados en el nombre del archivo o su carpeta padre
                            from collections import defaultdict
                            groups: dict = defaultdict(lambda: {k: [] for k in ['concessions','dsc_concessions','quality','false_scan','dwc','fdps','daily']})
                            group_years: dict = {}

                            for ff in all_files:
                                fn = ff.name.lower()
                                # Intentar detectar centro+semana desde el archivo, luego desde la carpeta padre
                                ww, cc, yy = scorecard.extract_info_from_path(ff.name)
                                if ww == 'N/A':
                                    ww, cc, yy = scorecard.extract_info_from_path(ff.parent.name)
                                key = (cc, ww)
                                if yy and key not in group_years:
                                    group_years[key] = yy

                                if re.match(scorecard.Config.PATTERN_DSC_CONCESSIONS, fn, re.IGNORECASE):
                                    groups[key]['dsc_concessions'].append(str(ff))
                                elif re.match(scorecard.Config.PATTERN_CONCESSIONS, fn, re.IGNORECASE):
                                    groups[key]['concessions'].append(str(ff))
                                elif re.match(scorecard.Config.PATTERN_QUALITY, fn, re.IGNORECASE):
                                    groups[key]['quality'].append(str(ff))
                                elif re.match(scorecard.Config.PATTERN_FALSE_SCAN, fn, re.IGNORECASE):
                                    groups[key]['false_scan'].append(str(ff))
                                elif re.match(scorecard.Config.PATTERN_DWC, fn, re.IGNORECASE):
                                    groups[key]['dwc'].append(str(ff))
                                elif re.match(scorecard.Config.PATTERN_FDPS, fn, re.IGNORECASE):
                                    groups[key]['fdps'].append(str(ff))
                                elif re.match(scorecard.Config.PATTERN_DAILY, fn, re.IGNORECASE):
                                    groups[key]['daily'].append(str(ff))

                            sorted_groups = sorted(groups.items(), key=lambda x: (x[0][0], x[0][1]))
                            prog = st.progress(0)
                            total_folders = max(len(sorted_groups), 1)

                            for i, ((center_f, week_f), batch_files) in enumerate(sorted_groups):
                                year_f = group_years.get((center_f, week_f))

                                if not batch_files['concessions']:
                                    errors_bulk.append(f"⬜ {center_f} {week_f}: sin archivo Concessions")
                                    prog.progress((i+1)/total_folders)
                                    continue

                                # Obtener targets del centro
                                t_bulk = scorecard.get_center_targets(center_f, db_config=db_config)

                                df_bulk = scorecard.process_single_batch(
                                    batch_files['concessions'],
                                    batch_files['quality']          or None,
                                    batch_files['false_scan']       or None,
                                    batch_files['dwc']              or None,
                                    batch_files['fdps']             or None,
                                    batch_files['daily']            or None,
                                    path_dsc_concessions=batch_files.get('dsc_concessions') or None,
                                    targets=t_bulk
                                )

                                if df_bulk is not None:
                                    _year_to_save_b = year_f if year_f else datetime.now().year
                                    ok_b, _err_b = scorecard.save_to_database(
                                        df_bulk, week_f, center_f,
                                        db_config=db_config,
                                        uploaded_by=f"{user_data_session['name']} (bulk)",
                                        year=_year_to_save_b,
                                    )
                                    status = "✅" if ok_b else "⚠️"
                                    _sfx = f" — {_err_b}" if not ok_b and _err_b else f" — {len(df_bulk)} conductores"
                                    results_bulk.append(
                                        f"{status} {center_f} {week_f}{_sfx}"
                                    )
                                    _audit(f"Bulk import: {center_f} {week_f} — {len(df_bulk)} conductores")
                                else:
                                    errors_bulk.append(f"❌ {center_f} {week_f}: error en procesamiento")

                                prog.progress((i+1)/total_folders)

                        prog.progress(1.0)

                        # Invalidar cachés
                        _clear_all_caches()

                        # Resumen
                        st.success(f"✅ Importación completada: {len(results_bulk)} lotes procesados.")
                        if results_bulk:
                            st.markdown("**Resultados:**")
                            for r in results_bulk:
                                st.markdown(f"- {r}")
                        if errors_bulk:
                            st.markdown("**Carpetas con problemas:**")
                            for e in errors_bulk:
                                st.markdown(f"- {e}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: DSP SCORECARD PDF (sin cambios funcionales)
# ─────────────────────────────────────────────────────────────────────────────

if tab_dsp:
    with tab_dsp:
        st.header("📋 PDFs Semanales")

        _last_result = st.session_state.pop('_dsp_last_result', None)
        if _last_result:
            all_ok = all(r.startswith("✅") for r in _last_result)
            msg = "**PDFs guardados correctamente:**\n\n" + "\n\n".join(_last_result)
            if all_ok:
                st.success(msg)
            else:
                st.warning(msg)

        _uploader_key = f"dsp_uploader_{st.session_state.get('_dsp_uploader_reset', 0)}"
        uploaded_pdfs = st.file_uploader(
            "Seleccionar PDFs (puedes subir varios a la vez)",
            type=["pdf"], accept_multiple_files=True,
            key=_uploader_key
        )

        if uploaded_pdfs:
            # ── PASO 1: Parsear todos los PDFs de una vez ─────────────────
            _pdf_key = f"_dsp_parsed_{','.join(f.name for f in uploaded_pdfs)}"
            if st.session_state.get('_dsp_pdf_key') != _pdf_key:
                _all_parsed = []
                _prog = st.progress(0, text="Procesando PDFs...")
                for _i, _pdf_file in enumerate(uploaded_pdfs):
                    _prog.progress((_i) / len(uploaded_pdfs), text=f"Leyendo {_pdf_file.name}...")
                    _p = scorecard.parse_dsp_scorecard_pdf(_pdf_file.read())
                    _p['_filename'] = _pdf_file.name
                    _all_parsed.append(_p)
                _prog.progress(1.0, text="✅ Procesados")
                st.session_state['_dsp_pdf_key']    = _pdf_key
                st.session_state['_dsp_all_parsed'] = _all_parsed

            _all_parsed = st.session_state.get('_dsp_all_parsed', [])
            _tier_color = {'Fantastic': '🔵', 'Great': '🟢', 'Fair': '🟠', 'Poor': '🔴'}
            _AMAZON_COLORS = {
                'Fantastic': '#0F6CBD',
                'Great':     '#067D50',
                'Fair':      '#FF9900',
                'Poor':      '#CC0000',
            }

            def _amz_badge(tier: str) -> str:
                c = _AMAZON_COLORS.get(tier, '#6c757d')
                return (f'<span style="background:{c};color:#fff;padding:2px 8px;'
                        f'border-radius:3px;font-size:.78em;font-weight:600">{tier or "—"}</span>')

            def _block_hdr(icon: str, title: str, tier: str | None = None) -> str:
                c = _AMAZON_COLORS.get(tier, '#495057')
                badge = f' {_amz_badge(tier)}' if tier else ''
                return (f'<div style="background:#f0f2f6;border-left:4px solid {c};'
                        f'padding:6px 12px;border-radius:4px;margin:12px 0 4px 0;font-weight:600">'
                        f'{icon} {title}{badge}</div>')

            def _sub_hdr(title: str) -> str:
                return (f'<div style="color:#6c757d;font-size:.8em;font-weight:700;'
                        f'margin:8px 0 2px 0;text-transform:uppercase;letter-spacing:.5px">'
                        f'{title}</div>')

            _ok_parsed  = [p for p in _all_parsed if p['ok']]
            _err_parsed = [p for p in _all_parsed if not p['ok']]

            # ── PASO 2: Resumen compacto ──────────────────────────────────
            if _err_parsed:
                for _p in _err_parsed:
                    st.error(f"❌ **{_p['_filename']}** — {', '.join(_p['errors'])}")

            if _ok_parsed:
                # Tabla resumen rápida
                _summary_rows = []
                for _p in _ok_parsed:
                    _m = _p['meta']
                    _s = _p['station']
                    _icon = _tier_color.get(_s.get('overall_standing', ''), '⚪')
                    _summary_rows.append({
                        'Centro':    _m['centro'],
                        'Semana':    f"{_m['semana']}/{_m.get('year', '')}",
                        'Score':     _s.get('overall_score', '—'),
                        'Standing':  f"{_icon} {_s.get('overall_standing', '—')}",
                        'Rank':      f"#{_s.get('rank_station', '—')}",
                        'Drivers':   len(_p['drivers']) if not _p['drivers'].empty else 0,
                        'WHC':       len(_p['wh']) if not _p['wh'].empty else 0,
                        'Avisos':    len(_p['errors']),
                    })
                st.dataframe(
                    pd.DataFrame(_summary_rows),
                    use_container_width=True, hide_index=True
                )

                # ── PASO 3: BOTÓN ÚNICO "GUARDAR TODOS" ──────────────────
                _n_pdfs   = len(_ok_parsed)
                _pdf_names = [p['meta']['centro'] + ' ' + p['meta']['semana'] for p in _ok_parsed]
                if _n_pdfs <= 3:
                    _names_str = ', '.join(_pdf_names)
                else:
                    _names_str = ', '.join(_pdf_names[:3]) + f' … y {_n_pdfs - 3} más'
                _btn_label = f"💾 Guardar {_n_pdfs} PDF{'s' if _n_pdfs > 1 else ''} — {_names_str}"
                if st.button(_btn_label, type="primary", use_container_width=True,
                             key="save_all_pdfs"):
                    _save_prog = st.progress(0, text="Guardando...")
                    _save_results = []
                    for _i, _p in enumerate(_ok_parsed):
                        _m = _p['meta']
                        _s = _p['station']
                        _c, _w, _yr = _m['centro'], _m['semana'], _m.get('year')
                        if _yr is None:
                            _yr = 2025
                        try:
                            _ok_st, _err_st = scorecard.save_station_scorecard(
                                _s, _w, _c, db_config, user_data_session['name'],
                                year=_yr)
                            _n_upd, _n_miss = scorecard.update_drivers_from_pdf(
                                _p['drivers'], _w, _c, db_config, year=_yr)
                            _ok_wh = scorecard.save_wh_exceptions(
                                _p['wh'], _w, _c, db_config, user_data_session['name'],
                                year=_yr)
                            if _ok_st:
                                _audit(f"Guardó PDF DSP {_c} {_w}")
                                _save_results.append(
                                    f"✅ **{_c} {_w}** — {_n_upd} drivers · "
                                    f"{'✅' if _ok_wh else '⚠️'} WHC"
                                )
                            else:
                                _save_results.append(
                                    f"❌ **{_c} {_w}** — Scorecard no guardado: `{_err_st}`"
                                )
                        except Exception as _e:
                            _save_results.append(f"❌ **{_c} {_w}** — Error: {_e}")
                        _save_prog.progress((_i + 1) / len(_ok_parsed))

                    _clear_all_caches()
                    st.session_state.pop('_dsp_pdf_key', None)
                    st.session_state.pop('_dsp_all_parsed', None)
                    st.session_state['_dsp_uploader_reset'] = st.session_state.get('_dsp_uploader_reset', 0) + 1
                    st.session_state['_dsp_last_result'] = _save_results
                    st.rerun()

                # ── PASO 4: Detalle por PDF (oculto por defecto) ────────────
                st.markdown("---")
                _show_detail = st.checkbox(
                    "🔍 Ver detalle completo por PDF",
                    value=False,
                    key=f"_dsp_show_detail_{_pdf_key[:40]}"
                )
                if _show_detail:
                    for _p in _ok_parsed:
                        _m = _p['meta']
                        _s = _p['station']
                        _icon = _tier_color.get(_s.get('overall_standing', ''), '⚪')
                        _exp_title = (
                            f"{_icon} {_m['centro']} — {_m['semana']}/{_m.get('year','')} · "
                            f"Score {_s.get('overall_score')} ({_s.get('overall_standing')}) · "
                            f"Rank #{_s.get('rank_station')}"
                        )
                        with st.expander(_exp_title, expanded=False):
                            _rw  = _s.get('rank_wow')
                            _tc  = _tier_color
                            _ost = _s.get('overall_standing', '')

                            # ── Overall ──────────────────────────────────────────
                            _ov1, _ov2 = st.columns([3, 1])
                            with _ov1:
                                st.markdown(
                                    f"<div style='font-size:1.5em;font-weight:700;margin-bottom:4px'>"
                                    f"Score: {_s.get('overall_score', '—')} &nbsp;"
                                    f"{_amz_badge(_ost)}</div>",
                                    unsafe_allow_html=True
                                )
                            with _ov2:
                                _wow_txt = f"{_rw:+d} WoW" if _rw is not None else None
                                st.metric("Ranking", f"#{_s.get('rank_station', '—')}", _wow_txt)

                            # ── Compliance & Safety ───────────────────────────────
                            st.markdown(_block_hdr("🛡️", "Compliance & Safety",
                                                   _s.get('safety_tier')), unsafe_allow_html=True)

                            st.markdown(_sub_hdr("Safety"), unsafe_allow_html=True)
                            _sa1, _sa2, _sa3 = st.columns(3)
                            _sa1.metric(f"FICO {_tc.get(_s.get('fico_tier',''),'⚪')}",
                                        _s.get('fico'), _s.get('fico_tier'))
                            _sa2.metric(f"Speeding {_tc.get(_s.get('speeding_tier',''),'⚪')}",
                                        _s.get('speeding_rate'), _s.get('speeding_tier'))
                            _ment = _s.get('mentor_adoption')
                            _sa3.metric(f"Mentor {_tc.get(_s.get('mentor_tier',''),'⚪')}",
                                        f"{_ment}%" if _ment is not None else "—",
                                        _s.get('mentor_tier'))

                            st.markdown(_sub_hdr("Compliance"), unsafe_allow_html=True)
                            _co1, _co2, _co3, _co4 = st.columns(4)
                            _vsa = _s.get('vsa_compliance')
                            _co1.metric(f"VSA {_tc.get(_s.get('vsa_tier',''),'⚪')}",
                                        f"{_vsa}%" if _vsa is not None else "—",
                                        _s.get('vsa_tier'))
                            _boc_val   = _s.get('boc') or '—'
                            _boc_color = '#CC0000' if _boc_val == 'Yes' else '#067D50'
                            _co2.markdown(
                                f"<p style='font-size:.85em;margin:0;color:#6c757d'>BOC</p>"
                                f"<span style='background:{_boc_color};color:#fff;padding:3px 10px;"
                                f"border-radius:3px;font-size:.9em;font-weight:600'>{_boc_val}</span>",
                                unsafe_allow_html=True
                            )
                            _whc = _s.get('whc_pct')
                            _co3.metric(f"WHC {_tc.get(_s.get('whc_tier',''),'⚪')}",
                                        f"{_whc}%" if _whc is not None else "—",
                                        _s.get('whc_tier'))
                            _cas_val   = _s.get('cas') or '—'
                            _cas_color = ('#067D50' if 'Compliance' in _cas_val
                                          else '#CC0000' if 'Non' in _cas_val else '#6c757d')
                            _co4.markdown(
                                f"<p style='font-size:.85em;margin:0;color:#6c757d'>CAS</p>"
                                f"<span style='background:{_cas_color};color:#fff;padding:3px 10px;"
                                f"border-radius:3px;font-size:.9em;font-weight:600'>{_cas_val}</span>",
                                unsafe_allow_html=True
                            )

                            # ── Delivery Quality & SWC ───────────────────────────
                            st.markdown(_block_hdr("📦", "Delivery Quality & SWC",
                                                   _s.get('quality_tier')), unsafe_allow_html=True)

                            st.markdown(_sub_hdr("Customer Delivery Experience"), unsafe_allow_html=True)
                            _cx1, _cx2 = st.columns(2)
                            _cx1.metric(f"CE DPMO {_tc.get(_s.get('ce_tier',''),'⚪')}",
                                        _s.get('ce_dpmo'), _s.get('ce_tier'))
                            _cx2.metric(f"CDF DPMO {_tc.get(_s.get('cdf_tier',''),'⚪')}",
                                        _s.get('cdf_dpmo'), _s.get('cdf_tier'))

                            st.markdown(_sub_hdr("Standard Work Compliance"), unsafe_allow_html=True)
                            _sw1, _sw2 = st.columns(2)
                            _pod = _s.get('pod_pct')
                            _sw1.metric(f"POD {_tc.get(_s.get('pod_tier',''),'⚪')}",
                                        f"{_pod}%" if _pod is not None else "—",
                                        _s.get('pod_tier'))
                            _cc  = _s.get('cc_pct')
                            _sw2.metric(f"CC {_tc.get(_s.get('cc_tier',''),'⚪')}",
                                        f"{_cc}%" if _cc is not None else "—",
                                        _s.get('cc_tier'))

                            st.markdown(_sub_hdr("Quality"), unsafe_allow_html=True)
                            _q1, _q2, _q3, _q4 = st.columns(4)
                            _dcr = _s.get('dcr_pct')
                            _q1.metric(f"DCR {_tc.get(_s.get('dcr_tier',''),'⚪')}",
                                       f"{_dcr}%" if _dcr is not None else "—",
                                       _s.get('dcr_tier'))
                            _q2.metric(f"DNR DPMO {_tc.get(_s.get('dnr_tier',''),'⚪')}",
                                       _s.get('dnr_dpmo'), _s.get('dnr_tier'))
                            _q3.metric(f"LoR DPMO {_tc.get(_s.get('lor_tier',''),'⚪')}",
                                       _s.get('lor_dpmo'), _s.get('lor_tier'))
                            _q4.metric(f"DSC DPMO {_tc.get(_s.get('dsc_tier',''),'⚪')}",
                                       _s.get('dsc_dpmo'), _s.get('dsc_tier'))

                            # ── Capacity ─────────────────────────────────────────
                            st.markdown(_block_hdr("🚛", "Capacity",
                                                   _s.get('capacity_tier')), unsafe_allow_html=True)
                            _cap1, _cap2 = st.columns(2)
                            _nd_val = _s.get('capacity_next_day')
                            _cap1.metric(f"Next Day {_tc.get(_s.get('capacity_next_day_tier',''),'⚪')}",
                                         f"{_nd_val}%" if _nd_val is not None else "—",
                                         _s.get('capacity_next_day_tier'))
                            _sd_val = _s.get('capacity_same_day')
                            if _sd_val is not None:
                                _cap2.metric(f"Same Day {_tc.get(_s.get('capacity_same_day_tier',''),'⚪')}",
                                             f"{_sd_val}%", _s.get('capacity_same_day_tier'))

                            # ── Focus Areas ──────────────────────────────────────
                            _fa1 = _s.get('focus_area_1') or '—'
                            _fa2 = _s.get('focus_area_2') or '—'
                            _fa3 = _s.get('focus_area_3') or '—'
                            st.markdown(
                                f"<div style='background:#fff3cd;border-left:4px solid #FF9900;"
                                f"padding:8px 12px;border-radius:4px;margin:12px 0 6px 0'>"
                                f"🎯 <b>Focus Areas Amazon:</b>&nbsp; "
                                f"1. {_fa1} &nbsp;·&nbsp; 2. {_fa2} &nbsp;·&nbsp; 3. {_fa3}</div>",
                                unsafe_allow_html=True
                            )

                            _nd = len(_p['drivers']) if not _p['drivers'].empty else 0
                            _nw = len(_p['wh']) if not _p['wh'].empty else 0
                            st.caption(f"📊 {_nd} conductores · ⏰ {_nw} excepciones WHC")
                            if _p['errors']:
                                st.warning(f"⚠️ Campos no encontrados: {', '.join(_p['errors'])}")

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
                # Columna semana/año combinada: "W09/2026"
                if 'anio' in df_filtrado.columns:
                    df_filtrado = df_filtrado.copy()
                    _anio_ok = df_filtrado['anio'].notna() & (df_filtrado['anio'] != 0)
                    df_filtrado['semana_año'] = np.where(
                        _anio_ok,
                        df_filtrado['semana'] + '/' + df_filtrado['anio'].where(_anio_ok, 0).astype(int).astype(str),
                        df_filtrado['semana']
                    )
                    _semana_col = 'semana_año'
                else:
                    _semana_col = 'semana'

                _DSP_COL_RENAME = {
                    'overall_score':          'Score',
                    'overall_standing':       'Standing',
                    'rank_station':           'Rank',
                    'rank_wow':               'WoW',
                    'safety_tier':            'Safety',
                    'fico_tier':              'FICO Tier',
                    'speeding_rate':          'Speeding',
                    'speeding_tier':          'Speed Tier',
                    'mentor_adoption':        'Mentor %',
                    'mentor_tier':            'Mentor Tier',
                    'vsa_compliance':         'VSA %',
                    'vsa_tier':               'VSA Tier',
                    'whc_pct':                'WHC %',
                    'whc_tier':               'WHC Tier',
                    'wh_count':               'WHC Drv.',
                    'quality_tier':           'Quality',
                    'dcr_pct':                'DCR %',
                    'dcr_tier':               'DCR Tier',
                    'dnr_dpmo':               'DNR DPMO',
                    'dnr_tier':               'DNR Tier',
                    'lor_dpmo':               'LoR DPMO',
                    'lor_tier':               'LoR Tier',
                    'dsc_dpmo':               'DSC DPMO',
                    'dsc_tier':               'DSC Tier',
                    'pod_pct':                'POD %',
                    'pod_tier':               'POD Tier',
                    'cc_pct':                 'CC %',
                    'cc_tier':                'CC Tier',
                    'ce_dpmo':                'CE DPMO',
                    'ce_tier':                'CE Tier',
                    'cdf_dpmo':               'CDF DPMO',
                    'cdf_tier':               'CDF Tier',
                    'capacity_tier':          'Capacity',
                    'capacity_next_day':      'Next Day %',
                    'capacity_next_day_tier': 'ND Tier',
                    'focus_area_1':           'Focus 1',
                    'focus_area_2':           'Focus 2',
                    'focus_area_3':           'Focus 3',
                }
                _raw_cols = [_semana_col] + [c for c in [
                    'centro', 'overall_score', 'overall_standing', 'rank_station', 'rank_wow',
                    'safety_tier', 'fico', 'fico_tier', 'speeding_rate', 'speeding_tier',
                    'mentor_adoption', 'mentor_tier', 'vsa_compliance', 'vsa_tier',
                    'boc', 'whc_pct', 'whc_tier', 'wh_count', 'cas',
                    'quality_tier', 'dcr_pct', 'dcr_tier', 'dnr_dpmo', 'dnr_tier',
                    'lor_dpmo', 'lor_tier', 'dsc_dpmo', 'dsc_tier',
                    'pod_pct', 'pod_tier', 'cc_pct', 'cc_tier',
                    'ce_dpmo', 'ce_tier', 'cdf_dpmo', 'cdf_tier',
                    'capacity_tier', 'capacity_next_day', 'capacity_next_day_tier',
                    'focus_area_1', 'focus_area_2', 'focus_area_3'
                ] if c in df_filtrado.columns]
                _semana_pretty = 'Semana' if _semana_col == 'semana' else 'Semana/Año'
                _rename_map    = {_semana_col: _semana_pretty, **{k: v for k, v in _DSP_COL_RENAME.items() if k in _raw_cols}}
                df_display     = df_filtrado[_raw_cols].rename(columns=_rename_map)
                cols_show      = df_display.columns.tolist()
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )

                # ── GRÁFICO 1: Ranking última semana ────────────────────────
                st.markdown("---")
                st.subheader("🏆 Ranking Overall Score — Última Semana")
                st.caption("Score oficial del PDF DSP en la semana más reciente disponible por centro.")
                df_latest_ss = (df_ss.sort_values('fecha_semana', ascending=False)
                                .groupby('centro').first().reset_index())
                df_latest_ss['score_f'] = pd.to_numeric(df_latest_ss['overall_score'], errors='coerce')
                df_latest_ss = df_latest_ss.dropna(subset=['score_f']).sort_values('score_f', ascending=False)
                if not df_latest_ss.empty:
                    df_latest_ss['tier'] = df_latest_ss['overall_standing'].fillna('—')
                    df_latest_ss['label'] = df_latest_ss['score_f'].apply(lambda x: f"{x:.1f}")
                    _sort_ss = df_latest_ss['centro'].tolist()
                    _y_min_ss = max(0, float(df_latest_ss['score_f'].min()) - 10)
                    _y_max_ss = min(105, float(df_latest_ss['score_f'].max()) + 15)
                    _cs_ss = alt.Scale(domain=['Fantastic', 'Great', 'Fair', 'Poor', '—'],
                                       range=['#0F6CBD', '#067D50', '#FF9900', '#CC0000', '#6c757d'])
                    _bar_ss = min(60, max(20, 400 // max(1, len(df_latest_ss))))
                    _bars_ss = (alt.Chart(df_latest_ss)
                        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, size=_bar_ss)
                        .encode(
                            x=alt.X('centro:N', sort=_sort_ss,
                                    axis=alt.Axis(labelAngle=0, labelColor='white',
                                                  labelFontSize=13, labelFontWeight='bold',
                                                  titleColor='white', tickColor='white'),
                                    title='Centro'),
                            y=alt.Y('score_f:Q', scale=alt.Scale(domain=[_y_min_ss, _y_max_ss]),
                                    axis=alt.Axis(labelColor='white', titleColor='white'),
                                    title='Overall Score'),
                            color=alt.Color('tier:N', scale=_cs_ss,
                                            legend=alt.Legend(title='Standing', labelColor='white', titleColor='white')),
                            tooltip=[alt.Tooltip('centro:N', title='Centro'),
                                     alt.Tooltip('score_f:Q', title='Score', format='.1f'),
                                     alt.Tooltip('tier:N', title='Standing'),
                                     alt.Tooltip('semana:N', title='Semana')]
                        ).properties(height=300))
                    _text_ss = (alt.Chart(df_latest_ss)
                        .mark_text(dy=-10, fontSize=13, fontWeight='bold', color='white')
                        .encode(x=alt.X('centro:N', sort=_sort_ss),
                                y=alt.Y('score_f:Q', scale=alt.Scale(domain=[_y_min_ss, _y_max_ss])),
                                text=alt.Text('label:N')))
                    st.altair_chart(
                        (_bars_ss + _text_ss).properties(padding={"bottom": 60}),
                        use_container_width=True
                    )

                # ── GRÁFICO 2: Tendencia temporal ────────────────────────────
                st.markdown("---")
                st.subheader("📈 Evolución del Score — Por Centro")
                st.caption("Evolución semanal del Overall Score oficial del PDF DSP. Mínimo 2 semanas para mostrar.")
                _centros_ss = sorted(df_ss['centro'].dropna().unique().tolist())
                _sel_c_ss = st.selectbox("Seleccionar centro", _centros_ss, key="ss_trend_centro")
                df_tr_ss = df_ss[df_ss['centro'] == _sel_c_ss].copy()
                df_tr_ss['score_f'] = pd.to_numeric(df_tr_ss['overall_score'], errors='coerce')
                df_tr_ss = df_tr_ss.dropna(subset=['score_f', 'fecha_semana']).sort_values('fecha_semana')
                if len(df_tr_ss) < 2:
                    st.info("Se necesitan al menos 2 semanas de datos para mostrar la tendencia.")
                else:
                    if 'anio' in df_tr_ss.columns:
                        _aok = df_tr_ss['anio'].notna() & (df_tr_ss['anio'] != 0)
                        df_tr_ss['sem_lbl'] = np.where(
                            _aok,
                            df_tr_ss['semana'] + '/' + df_tr_ss['anio'].where(_aok, 0).astype(int).astype(str),
                            df_tr_ss['semana']
                        )
                    else:
                        df_tr_ss['sem_lbl'] = df_tr_ss['semana'].astype(str)
                    df_tr_ss['label'] = df_tr_ss['score_f'].apply(lambda x: f"{x:.1f}")
                    _sort_tr = df_tr_ss['sem_lbl'].tolist()
                    _y_lo = max(0, float(df_tr_ss['score_f'].min()) - 10)
                    _y_hi = min(105, float(df_tr_ss['score_f'].max()) + 15)
                    _line_ss = (alt.Chart(df_tr_ss)
                        .mark_line(strokeWidth=3, color='#FF9900', point=alt.OverlayMarkDef(color='#FF9900', size=80))
                        .encode(
                            x=alt.X('sem_lbl:N', sort=_sort_tr,
                                    axis=alt.Axis(labelAngle=-30, labelColor='white',
                                                  labelFontSize=11, titleColor='white'),
                                    title='Semana'),
                            y=alt.Y('score_f:Q', scale=alt.Scale(domain=[_y_lo, _y_hi]),
                                    axis=alt.Axis(labelColor='white', titleColor='white'),
                                    title='Score'),
                            tooltip=[alt.Tooltip('sem_lbl:N', title='Semana'),
                                     alt.Tooltip('score_f:Q', title='Score', format='.1f'),
                                     alt.Tooltip('overall_standing:N', title='Standing')]
                        ))
                    _txt_line = (alt.Chart(df_tr_ss)
                        .mark_text(dy=-15, fontSize=12, fontWeight='bold', color='white')
                        .encode(x=alt.X('sem_lbl:N', sort=_sort_tr),
                                y=alt.Y('score_f:Q', scale=alt.Scale(domain=[_y_lo, _y_hi])),
                                text=alt.Text('label:N')))
                    st.altair_chart(
                        (_line_ss + _txt_line).properties(height=280, padding={"bottom": 50}),
                        use_container_width=True
                    )

                # ── GRÁFICO 3: Heatmap KPIs ──────────────────────────────────
                st.markdown("---")
                st.subheader("🗺️ Estado de KPIs por Centro — Última Semana")
                st.caption("Tier de cada KPI clave en la semana más reciente. 🔵 Fantastic · 🟢 Great · 🟠 Fair · 🔴 Poor.")
                _TIER_COLS = {
                    'DCR': 'dcr_tier', 'DNR': 'dnr_tier', 'POD': 'pod_tier',
                    'CC': 'cc_tier', 'FICO': 'fico_tier', 'Speeding': 'speeding_tier',
                    'WHC': 'whc_tier', 'Mentor': 'mentor_tier',
                    'Safety': 'safety_tier', 'Quality': 'quality_tier',
                }
                _TIER_NUM = {'Fantastic': 4, 'Great': 3, 'Fair': 2, 'Poor': 1}
                _heat_rows = []
                for _, _hr in df_latest_ss.iterrows():
                    for _kpi, _col in _TIER_COLS.items():
                        _t = str(_hr.get(_col) or '—')
                        _heat_rows.append({'Centro': _hr['centro'], 'KPI': _kpi,
                                           'Tier': _t, 'num': _TIER_NUM.get(_t, 0)})
                if _heat_rows:
                    df_heat = pd.DataFrame(_heat_rows)
                    _kpi_order = list(_TIER_COLS.keys())
                    _centro_order = df_latest_ss['centro'].tolist()
                    _heat_cs = alt.Scale(domain=[0, 1, 2, 3, 4],
                                         range=['#3d3d3d', '#CC0000', '#FF9900', '#067D50', '#0F6CBD'])
                    _heat_ch = (alt.Chart(df_heat)
                        .mark_rect(stroke='#1e2530', strokeWidth=1)
                        .encode(
                            x=alt.X('KPI:N', sort=_kpi_order,
                                    axis=alt.Axis(labelColor='white', titleColor='white',
                                                  labelFontSize=11, labelAngle=-20)),
                            y=alt.Y('Centro:N', sort=_centro_order,
                                    axis=alt.Axis(labelColor='white', titleColor='white',
                                                  labelFontSize=12)),
                            color=alt.Color('num:Q', scale=_heat_cs, legend=None),
                            tooltip=[alt.Tooltip('Centro:N'), alt.Tooltip('KPI:N'),
                                     alt.Tooltip('Tier:N', title='Tier')]
                        ).properties(height=max(220, len(df_latest_ss) * 50)))
                    _text_heat = (alt.Chart(df_heat)
                        .mark_text(fontSize=11, fontWeight='bold', color='white')
                        .encode(x=alt.X('KPI:N', sort=_kpi_order),
                                y=alt.Y('Centro:N', sort=_centro_order),
                                text=alt.Text('Tier:N')))
                    st.altair_chart(
                        (_heat_ch + _text_heat).properties(padding={"bottom": 40}),
                        use_container_width=True
                    )

        except Exception as e:
            st.error(f"❌ Error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: SCORECARD (Vista principal para JTs — redesign completo)
# ─────────────────────────────────────────────────────────────────────────────

with tab_excel:
    st.header("📊 Scorecard Semanal")

    try:
        # Semanas visibles según rol
        # JTs: solo las 2 más recientes por timestamp de subida + filtro por centro asignado
        # Admins: todas
        # Semanas visibles según rol:
        # - JT: sus 2 semanas permitidas
        # - Admin: las últimas 4 semanas activas (BD conserva todo, la app solo muestra las más recientes)
        allowed = ALLOWED_WEEKS_JT if is_jt else None
        active_weeks = get_active_weeks(_DB_KEY, db_config) if not is_jt else None
        df_available = cached_available_batches(_DB_KEY, db_config, allowed,
                                                active_weeks_only=active_weeks)

        # Si el JT tiene centro asignado, filtrar también por centro
        if is_jt and JT_CENTRO and not df_available.empty:
            df_available = df_available[df_available['centro'] == JT_CENTRO]

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

            # Si cambia selector, refrescar Y resetear filtros activos
            if sc_week != selected_week or sc_center != selected_center:
                sc_week   = selected_week
                sc_center = selected_center
                # Limpiar filtros de calificación para que no queden "atascados"
                for _fk in ['cal_filter', 'calificacion_filter', 'filter_cal', 'sc_cal_filter']:
                    st.session_state.pop(_fk, None)

            df_sc = cached_scorecard(_DB_KEY, db_config, sc_week, sc_center)

            if df_sc.empty:
                st.warning("No se encontraron datos para este scorecard.")
            else:
                # ── Semana anterior para deltas WoW (caché 5 min) ──
                df_prev = cached_prev_week(_DB_KEY, db_config, sc_center, sc_week)
                prev_week = (
                    df_prev['semana'].iloc[0]
                    if not df_prev.empty and 'semana' in df_prev.columns else None
                )


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

                # Cobertura PDF oficial
                n_pdf_loaded = int(df_sc['pdf_loaded'].fillna(0).astype(int).sum()) if 'pdf_loaded' in df_sc.columns else 0
                pct_pdf      = round(n_pdf_loaded / total * 100, 0) if total else 0
                pdf_color    = "#198754" if pct_pdf == 100 else ("#fd7e14" if pct_pdf > 0 else "#6c757d")

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
                        <div style='text-align:right;font-size:0.85em'>
                            <div style='opacity:0.7'>{total} conductores</div>
                            <div style='margin-top:4px'>
                                <span style='background:{pdf_color};color:white;padding:2px 8px;
                                border-radius:10px;font-size:0.9em;font-weight:700'>
                                📄 PDF: {n_pdf_loaded}/{total} ({int(pct_pdf)}%)
                                </span>
                            </div>
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
                    (d1, 'FANTASTIC', n_fantastic, '#0d6efd'),
                    (d2, 'GREAT',     n_great,     '#198754'),
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

                # ══════════════════════════════════════════════════════════════
                # LISTA DE CONDUCTORES — Expander individual por DA
                # POOR/FAIR: abierto por defecto | GREAT/FANTASTIC: cerrado
                # ══════════════════════════════════════════════════════════════

                # ── Pre-cargar tendencia batch (caché 5 min) ──
                _df_trend_batch = cached_trend_batch(_DB_KEY, db_config, sc_center, TREND_WEEKS_BATCH)

                # Pre-computar HTML de tendencia — O(n) una vez fuera del loop de conductores
                _mini_trend_map: dict = {}
                if not _df_trend_batch.empty:
                    for _tid in _df_trend_batch['driver_id'].unique():
                        _mini_trend_map[str(_tid)] = _get_mini_trend(str(_tid), _df_trend_batch)

                # ── WoW delta por conductor (ya tenemos df_prev cargado) ───────
                wow_map = (
                    df_prev.set_index('driver_id')['score'].to_dict()
                    if not df_prev.empty and 'driver_id' in df_prev.columns
                    else {}
                )

                # ── Ordenar: POOR primero, luego FAIR, GREAT, FANTASTIC ────────
                _order = {'🛑 POOR': 0, '⚠️ FAIR': 1, '🥇 GREAT': 2, '💎 FANTASTIC': 3}
                df_all_sorted = df_sc.copy()
                df_all_sorted['_sort_cal'] = df_all_sorted['calificacion'].map(_order).fillna(4)
                df_all_sorted = df_all_sorted.sort_values(['_sort_cal', 'score']).reset_index(drop=True)

                # ── Filtro por calificación — st.radio horizontal (sin rerun) ──
                n_poor      = int((df_sc['calificacion'] == '🛑 POOR').sum())
                n_fair      = int((df_sc['calificacion'] == '⚠️ FAIR').sum())
                n_great     = int((df_sc['calificacion'] == '🥇 GREAT').sum())
                n_fantastic = int((df_sc['calificacion'] == '💎 FANTASTIC').sum())

                _radio_opts = [
                    f"Todos ({len(df_sc)})",
                    f"🛑 POOR ({n_poor})",
                    f"⚠️ FAIR ({n_fair})",
                    f"🥇 GREAT ({n_great})",
                    f"💎 FANTASTIC ({n_fantastic})",
                ]
                _radio_key = f"radio_filter_{sc_center}_{sc_week}"
                _radio_sel = st.radio(
                    "Filtrar:", _radio_opts, index=0,
                    horizontal=True, label_visibility="collapsed",
                    key=_radio_key
                )

                # Mapear selección a valor de calificación (None = todos)
                _cal_map = {
                    _radio_opts[0]: None,
                    _radio_opts[1]: '🛑 POOR',
                    _radio_opts[2]: '⚠️ FAIR',
                    _radio_opts[3]: '🥇 GREAT',
                    _radio_opts[4]: '💎 FANTASTIC',
                }
                _cal_activo = _cal_map.get(_radio_sel)

                if _cal_activo:
                    df_visible = df_all_sorted[df_all_sorted['calificacion'] == _cal_activo].copy()
                else:
                    df_visible = df_all_sorted

                # ── Paginación ─────────────────────────────────────────────────
                # Usar radio key como base — al cambiar filtro, resetear página
                _pk = f"page_{sc_center}_{sc_week}"
                _prev_filter_key = f"prev_filter_{sc_center}_{sc_week}"
                if (st.session_state.get(_prev_filter_key) != _cal_activo
                        or _pk not in st.session_state):
                    st.session_state[_pk] = 0
                st.session_state[_prev_filter_key] = _cal_activo

                _total_visible = len(df_visible)
                _n_pages = max(1, (_total_visible + DRIVERS_PER_PAGE - 1) // DRIVERS_PER_PAGE)
                _page = min(st.session_state[_pk], _n_pages - 1)
                st.session_state[_pk] = _page

                _start = _page * DRIVERS_PER_PAGE
                _end   = _start + DRIVERS_PER_PAGE
                df_page = df_visible.iloc[_start:_end]

                _pag_info = f"Página {_page + 1}/{_n_pages} · {_total_visible} conductores"
                if _cal_activo:
                    _pag_info += f" · {_cal_activo} — pulsa de nuevo para ver todos"
                else:
                    _pag_info += " · pulsa una categoría para filtrar"
                st.caption(_pag_info)

                if _n_pages > 1:
                    _render_pagination(
                        _pk, _page, _n_pages, _total_visible, DRIVERS_PER_PAGE,
                        prev_key=f'prev_{sc_center}_{sc_week}',
                        next_key=f'next_{sc_center}_{sc_week}',
                    )


                # ── Loop por conductor ─────────────────────────────────────────
                # ── _metric_row helper (definido fuera del loop) ─────────
                # Targets cacheados UNA VEZ fuera del loop (antes: 1 llamada por conductor)
                _t = cached_center_targets(_DB_KEY, db_config, sc_center)

                for _, row in df_page.iterrows():
                    cal       = str(row['calificacion'])
                    cal_color = CALIFICACION_COLORS.get(cal, '#6c757d')
                    is_poor   = cal == '🛑 POOR'
                    is_fair   = cal == '⚠️ FAIR'
                    is_great  = cal == '🥇 GREAT'
                    is_fantas = cal == '💎 FANTASTIC'
                    prev_score = wow_map.get(row['driver_id'])
                    wow_str    = ""
                    if prev_score is not None:
                        delta_s = row['score'] - prev_score
                        wow_icon = '▲' if delta_s > 0 else ('▼' if delta_s < 0 else '→')
                        wow_col  = '#198754' if delta_s >= 0 else '#dc3545'
                        wow_str  = f" <span style='color:{wow_col};font-size:0.85em'>{wow_icon}{delta_s:+.0f}</span>"

                    # Mini-tendencia
                    mini_trend = _mini_trend_map.get(str(row['driver_id']), '')

                    # Label del expander
                    exp_label = (
                        f"{cal.split(' ')[0]} {row['driver_name']}  ·  "
                        f"Score: {int(row['score'])}"
                        + (f" ({delta_s:+.0f} WoW)" if prev_score is not None else "")
                        + f"  ·  DNR: {int(row['dnr'])}  ·  DCR: {row['dcr']*100:.1f}%"
                    )

                    # POOR y FAIR abren por defecto; GREAT y FANTASTIC cerrados
                    with st.expander(exp_label, expanded=(is_poor or is_fair)):

                        # ── Cabecera: badge calificación + tendencia ───────────
                        _esc_name = _html.escape(str(row['driver_name']))
                        _esc_id   = _html.escape(str(row['driver_id']))
                        head_col1, head_col2 = st.columns([2, 3])
                        with head_col1:
                            st.markdown(
                                clean_html(f"""
                                <div style='background:{cal_color}15;border-left:4px solid {cal_color};
                                            border-radius:6px;padding:8px 12px;margin-bottom:4px'>
                                    <span style='font-size:1.1em;font-weight:800;color:{cal_color}'>{cal}</span>
                                    &nbsp;&nbsp;
                                    <span style='font-weight:700;color:#212529'>{_esc_name}</span>
                                    <br>
                                    <span style='font-size:0.82em;color:#6c757d'>ID: {_esc_id}</span>
                                </div>
                                """),
                                unsafe_allow_html=True
                            )
                        with head_col2:
                            if mini_trend:
                                st.markdown(
                                    f"<div style='padding-top:6px'>"
                                    f"<span style='font-size:0.8em;color:#6c757d;font-weight:600'>Últimas semanas: </span>"
                                    f"{mini_trend}</div>",
                                    unsafe_allow_html=True
                                )

                        st.markdown("---")

                        # ── Bloque principal: CSV vs PDF ───────────────────────
                        has_pdf = int(row.get('pdf_loaded', 0) or 0) == 1

                        _cols = st.columns([3, 2]) if has_pdf else st.columns([1])
                        col_csv = _cols[0]
                        col_pdf = _cols[1] if has_pdf else None

                        with col_csv:
                            st.markdown(
                                "<div style='font-weight:700;color:#adb5bd;margin-bottom:8px'>"
                                "📂 Informes Semanales (CSVs)</div>",
                                unsafe_allow_html=True
                            )
                            # Obtener targets del centro para mostrar vs objetivo

                            _rows = (
                                _metric_row("Entregas", row.get('entregados'), None, is_int=True, is_pct=False) +
                                _metric_row("DNR", row.get('dnr'), _t.get('target_dnr', 0.5),
                                            higher_is_better=False, is_pct=False, is_int=True) +
                                _metric_row("False Scans", row.get('fs_count'), 5,
                                            higher_is_better=False, is_pct=False, is_int=True) +
                                _metric_row("DCR", row.get('dcr'), _t.get('target_dcr', 0.995)) +
                                _metric_row("POD", row.get('pod'), _t.get('target_pod', 0.99)) +
                                _metric_row("CC",  row.get('cc'),  _t.get('target_cc', 0.99)) +
                                _metric_row("FDPS", row.get('fdps'), _t.get('target_fdps', 0.9)) +
                                _metric_row("RTS", row.get('rts'), _t.get('target_rts', 0.03),
                                            higher_is_better=False) +
                                _metric_row("CDF", row.get('cdf'), _t.get('target_cdf', 0.9))
                            )
                            st.markdown(clean_html(f"""
<table style='width:100%;border-collapse:collapse;background:#1a1f2e;
              border-radius:8px;overflow:hidden;border:1px solid #2d3748'>
<tbody>{_rows}</tbody>
</table>
"""), unsafe_allow_html=True)

                        if col_pdf is not None:
                            with col_pdf:
                                st.markdown(
                                    "<div style='font-weight:700;color:#ffc107;margin-bottom:6px'>"
                                    "🏆 Scorecard Oficial Amazon (PDF)</div>",
                                    unsafe_allow_html=True
                                )
                                if has_pdf:
                                    pdf_rows = [
                                        ("Entregas",         _fmt_num(row.get('entregados_oficial')),
                                         _diff_badge(row.get('entregados'), row.get('entregados_oficial'), is_pct=False)
                                         if row.get('entregados') else ""),
                                        ("DCR oficial",      _fmt_pct(row.get('dcr_oficial')),
                                         _diff_badge(row.get('dcr'), row.get('dcr_oficial')) if row.get('dcr') else ""),
                                        ("POD oficial",      _fmt_pct(row.get('pod_oficial')),
                                         _diff_badge(row.get('pod'), row.get('pod_oficial')) if row.get('pod') else ""),
                                        ("CC oficial",       _fmt_pct(row.get('cc_oficial')),
                                         _diff_badge(row.get('cc'), row.get('cc_oficial')) if row.get('cc') else ""),
                                        ("CDF DPMO",         _fmt_num(row.get('cdf_dpmo_oficial')),     ""),
                                        ("LOR DPMO",         _fmt_num(row.get('lor_dpmo')),             ""),
                                        ("DSC DPMO",         _fmt_num(row.get('dsc_dpmo')),             ""),
                                    ]
                                    pdf_html_rows = ""
                                    for label, val, diff in pdf_rows:
                                        pdf_html_rows += (
                                            f"<tr>"
                                            f"<td style='padding:5px 8px;color:#6c757d;font-size:0.85em;font-weight:600'>{label}</td>"
                                            f"<td style='padding:5px 8px;font-weight:700;text-align:right'>{val}</td>"
                                            f"<td style='padding:5px 8px;font-size:0.8em;text-align:right'>{diff}</td>"
                                            f"</tr>"
                                        )
                                    st.markdown(clean_html(f"""
                                    <table style='width:100%;border-collapse:collapse;
                                                  border:1px solid #198754;border-radius:6px;overflow:hidden'>
                                        <thead>
                                            <tr style='background:#19875415'>
                                                <th style='padding:5px 8px;text-align:left;
                                                           font-size:0.78em;color:#198754'>Métrica</th>
                                                <th style='padding:5px 8px;text-align:right;
                                                           font-size:0.78em;color:#198754'>Valor PDF</th>
                                                <th style='padding:5px 8px;text-align:right;
                                                           font-size:0.78em;color:#198754'>Δ CSV→PDF</th>
                                            </tr>
                                        </thead>
                                        <tbody>{pdf_html_rows}</tbody>
                                    </table>
                                    <div style='font-size:0.75em;color:#6c757d;margin-top:4px'>
                                        ✅ Diferencia pequeña · 🟡 Diferencia moderada · 🔴 Diferencia significativa
                                    </div>
                                    """), unsafe_allow_html=True)
                                else:
                                    st.markdown(
                                    "<div style='background:#f8f9fa;border:1px dashed #ced4da;"
                                    "border-radius:6px;padding:16px;text-align:center;"
                                    "color:#6c757d;font-size:0.88em'>"
                                    "⬜ PDF oficial no cargado para este conductor"
                                    "</div>",
                                    unsafe_allow_html=True
                                    )

                        # ── Penalizaciones / Reconocimiento ───────────────────
                        st.markdown("---")

                        if is_poor or is_fair:
                            # Problemas detectados
                            det_str = str(row.get('detalles', ''))
                            if det_str and det_str not in ('Óptimo', 'nan', ''):
                                st.markdown("**🔍 Problemas detectados:**")
                                st.markdown(render_detalles(det_str), unsafe_allow_html=True)

                            # Tips de coaching
                            tips = []
                            if 'DNR' in det_str or '🚨' in det_str:
                                tips.append("📌 **DNR:** Revisar rutas difícil acceso. Llamar al cliente antes de intentar entrega.")
                            if 'DCR' in det_str or '📦' in det_str:
                                tips.append("📌 **DCR:** Auditar intentos fallidos. Verificar estados correctos en la app.")
                            if 'POD' in det_str or '📸' in det_str:
                                tips.append("📌 **POD:** Foto obligatoria en CADA entrega, visible y sin ambigüedad.")
                            if 'FS' in det_str or '❌' in det_str:
                                tips.append("📌 **False Scans:** No escanear en la furgoneta. Solo en el punto exacto de entrega.")
                            if 'CC' in det_str or '📞' in det_str:
                                tips.append("📌 **CC:** Contactar al cliente cuando el acceso sea difícil. Registrar el intento.")
                            if 'RTS' in det_str or '🔄' in det_str:
                                tips.append("📌 **RTS:** Reducir devoluciones. Verificar direcciones antes de salir.")
                            if 'FDPS' in det_str or '🚚' in det_str:
                                tips.append("📌 **FDPS:** Maximizar entregas en primera visita. Planificar bien la ruta.")
                            if tips:
                                st.info("**💬 Puntos para la conversación:**\n\n" + "\n\n".join(tips))

                        elif is_great or is_fantas:
                            # Reconocimiento
                            rec_msgs = []
                            if is_fantas:
                                rec_msgs.append("🏆 **Rendimiento FANTASTIC** — Está en el nivel más alto posible.")
                                rec_msgs.append("✨ Reconocer su consistencia y compartir sus buenas prácticas con el equipo.")
                            else:
                                rec_msgs.append("🥇 **Rendimiento GREAT** — Por encima de los objetivos en la mayoría de métricas.")
                                rec_msgs.append("🎯 Mencionar qué hace bien y motivarle a alcanzar FANTASTIC la próxima semana.")

                            det_str = str(row.get('detalles', ''))
                            if det_str and det_str not in ('Óptimo', 'nan', ''):
                                rec_msgs.append(f"⚠️ **Áreas de mejora:** {det_str}")

                            st.success("\n\n".join(rec_msgs))

                # ── Descarga Excel (solo admins) ──────────────────────────
                if is_admin:
                    st.markdown("---")
                    output = io.BytesIO()
                    # Columnas base + oficiales del PDF cuando estén disponibles
                    excel_cols = [
                        'driver_name', 'driver_id', 'calificacion', 'score', 'entregados',
                        'dnr', 'fs_count', 'dnr_risk_events', 'dcr', 'pod', 'cc',
                        'fdps', 'rts', 'cdf', 'detalles',
                        'pdf_loaded', 'entregados_oficial', 'dcr_oficial',
                        'pod_oficial', 'cc_oficial', 'cdf_dpmo_oficial',
                        'dsc_dpmo', 'lor_dpmo', 'ce_dpmo',
                    ]
                    # Incluir solo las columnas que existan en df_sc
                    excel_cols = [c for c in excel_cols if c in df_sc.columns]
                    df_for_excel = df_sc[excel_cols].copy()
                    col_names = {
                        'driver_name': 'Nombre', 'driver_id': 'ID',
                        'calificacion': 'CALIFICACION', 'score': 'SCORE',
                        'entregados': 'Entregados', 'dnr': 'DNR',
                        'fs_count': 'FS_Count', 'dnr_risk_events': 'DNR_RISK_EVENTS',
                        'dcr': 'DCR', 'pod': 'POD', 'cc': 'CC',
                        'fdps': 'FDPS', 'rts': 'RTS', 'cdf': 'CDF', 'detalles': 'DETALLES',
                        'pdf_loaded': 'PDF_Cargado',
                        'entregados_oficial': 'Entregados_Oficial_PDF',
                        'dcr_oficial': 'DCR_Oficial_PDF',
                        'pod_oficial': 'POD_Oficial_PDF',
                        'cc_oficial': 'CC_Oficial_PDF',
                        'cdf_dpmo_oficial': 'CDF_DPMO_Oficial',
                        'dsc_dpmo': 'DSC_DPMO', 'lor_dpmo': 'LOR_DPMO', 'ce_dpmo': 'CE_DPMO',
                    }
                    df_for_excel.rename(columns={k: v for k, v in col_names.items() if k in df_for_excel.columns}, inplace=True)
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
                    (df_sc['driver_name'] + ' (' + df_sc['driver_id'] + ')').tolist(),
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

                    if df_trend.empty or len(df_trend) < 1:
                        st.info("ℹ️ Este conductor solo tiene datos de la semana actual. Necesitas al menos 2 semanas para ver tendencia.")
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

                        # ── Gráfico de score histórico con zonas de referencia ──
                        st.markdown("**📊 Score histórico**")
                        _df_plot = df_trend[['semana', 'score']].copy()
                        _sc_min = max(0, float(_df_plot['score'].min()) - 10)
                        _sc_max = min(100, float(_df_plot['score'].max()) + 10)

                        # Línea del score real
                        _line_score = (alt.Chart(_df_plot)
                            .mark_line(strokeWidth=3, color='#e85d04', point=alt.OverlayMarkDef(color='#e85d04', size=60))
                            .encode(
                                x=alt.X('semana:N', title='Semana'),
                                y=alt.Y('score:Q', scale=alt.Scale(domain=[_sc_min, _sc_max]), title='Score'),
                                tooltip=[alt.Tooltip('semana:N'), alt.Tooltip('score:Q', format='.0f', title='Score')]
                            ))
                        # Líneas de umbral como reglas horizontales
                        _thresholds = pd.DataFrame([
                            {'y': 90, 'label': 'FANTASTIC', 'color': '#0d6efd'},
                            {'y': 80, 'label': 'GREAT',     'color': '#198754'},
                            {'y': 60, 'label': 'FAIR',      'color': '#fd7e14'},
                        ])
                        _lines_ref = (alt.Chart(_thresholds)
                            .mark_rule(strokeDash=[4, 4], opacity=0.6)
                            .encode(
                                y=alt.Y('y:Q'),
                                color=alt.Color('color:N', scale=None, legend=None),
                                tooltip=[alt.Tooltip('label:N', title='Zona'), alt.Tooltip('y:Q', title='Umbral')]
                            ))
                        st.altair_chart((_lines_ref + _line_score).properties(height=280),
                                        use_container_width=True)

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
                                    '💎 FANTASTIC': '#f0f4ff',
                                    '🥇 GREAT':     '#f0fff4',
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

                        with st.expander("📊 Ver evolución de DNR / DCR / POD"):
                            _df_m = df_trend[['semana','dnr','dcr','pod']].copy()
                            _df_m['DCR (%)'] = (_df_m['dcr'] * 100).round(2)
                            _df_m['POD (%)'] = (_df_m['pod'] * 100).round(2)
                            # Gráfico DNR
                            st.markdown("**DNR por semana**")
                            _dnr_max = max(2.0, float(_df_m['dnr'].max()) * 1.4)
                            st.altair_chart(
                                alt.Chart(_df_m).mark_line(point=True, strokeWidth=2, color='#dc3545')
                                .encode(x=alt.X('semana:N', title=''),
                                        y=alt.Y('dnr:Q', scale=alt.Scale(domain=[0, _dnr_max]), title='DNR'),
                                        tooltip=[alt.Tooltip('semana:N'), alt.Tooltip('dnr:Q', format='.0f')])
                                .properties(height=160), use_container_width=True
                            )
                            # Gráfico DCR y POD juntos
                            st.markdown("**DCR y POD (%)**")
                            _df_pct = _df_m[['semana','DCR (%)','POD (%)']].melt('semana', var_name='Métrica', value_name='Valor')
                            _pct_min = max(80, float(_df_pct['Valor'].min()) - 2)
                            st.altair_chart(
                                alt.Chart(_df_pct).mark_line(point=True, strokeWidth=2)
                                .encode(x=alt.X('semana:N', title=''),
                                        y=alt.Y('Valor:Q', scale=alt.Scale(domain=[_pct_min, 100.5]), title='%'),
                                        color=alt.Color('Métrica:N', scale=alt.Scale(
                                            domain=['DCR (%)','POD (%)'],
                                            range=['#0d6efd','#198754'])),
                                        tooltip=[alt.Tooltip('semana:N'), alt.Tooltip('Métrica:N'),
                                                 alt.Tooltip('Valor:Q', format='.2f')])
                                .properties(height=160), use_container_width=True
                            )

    except Exception as e:
        st.error(f"❌ Error cargando el scorecard: {e}")
        st.exception(e)

# ─────────────────────────────────────────────────────────────────────────────
# TAB: HISTÓRICO
# ─────────────────────────────────────────────────────────────────────────────

with tab_hist:
    st.header("📈 Histórico de Scorecards")
    st.caption("Consulta y filtra todos los scorecards procesados. Usa los filtros para buscar por centro, semana, calificación o nombre de conductor.")

    col_ref, _ = st.columns([1, 5])
    with col_ref:
        if st.button("🔄 Actualizar datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    try:
        # JTs: solo semanas permitidas + centro asignado si tiene. Admins: todo.
        allowed_hist = ALLOWED_WEEKS_JT if is_jt else None
        df_meta = cached_meta(_DB_KEY, db_config, allowed_hist)

        # Filtrar metas por centro asignado al JT
        if is_jt and JT_CENTRO and not df_meta.empty:
            df_meta = df_meta[df_meta['centro'] == JT_CENTRO]

        if is_jt and allowed_hist:
            st.info(
                f"👔 Mostrando datos de: **{' y '.join(allowed_hist)}** "
                f"(semana en curso y anterior)"
            )

        if df_meta.empty:
            st.info("📭 No hay datos. Procesa archivos primero o pulsa **🔄 Actualizar datos** si acabas de subir archivos.")
        else:
            # ── Fila 1: filtros básicos ────────────────────────────────────
            col1, col2, col3 = st.columns(3)
            with col1:
                f_center = st.multiselect("🏢 Centro", sorted(df_meta['centro'].unique()))
            with col2:
                f_week = st.multiselect("📅 Semana", sorted(df_meta['semana'].unique(), reverse=True))
            with col3:
                f_calif = st.multiselect("🏆 Calificación", df_meta['calificacion'].unique())

            search_term = st.text_input("🔍 Buscar conductor", placeholder="Nombre o ID...")

            # ── Fila 2: filtros avanzados ──────────────────────────────────
            with st.expander("🔬 Filtros avanzados", expanded=False):
                fa1, fa2, fa3 = st.columns(3)
                with fa1:
                    # Tipo de problema — búsqueda en columna detalles
                    PROBLEMAS_OPCIONES = {
                        "DNR":         "DNR",
                        "DCR bajo":    "DCR",
                        "POD bajo":    "POD",
                        "False Scans": "FS",
                        "CC bajo":     "CC Bajo",
                        "RTS alto":    "RTS",
                        "FDPS bajo":   "FDPS",
                        "CDF bajo":    "CDF",
                    }
                    f_problemas = st.multiselect(
                        "🔍 Tipo de problema",
                        list(PROBLEMAS_OPCIONES.keys()),
                        help="Filtra conductores que tienen ese problema en sus detalles"
                    )
                with fa2:
                    f_dnr_min = st.number_input(
                        "⚡ DNR mínimo",
                        min_value=0, max_value=20, value=0, step=1,
                        help="Muestra solo conductores con DNR ≥ este valor"
                    )
                    f_score_max = st.number_input(
                        "📉 Score máximo",
                        min_value=0, max_value=100, value=100, step=5,
                        help="Muestra solo conductores con score ≤ este valor"
                    )
                with fa3:
                    f_dcr_max = st.number_input(
                        "📦 DCR máximo (%)",
                        min_value=80.0, max_value=100.0, value=100.0, step=0.1,
                        format="%.1f",
                        help="Muestra conductores con DCR ≤ este % (ej: 99.0 muestra los que tienen DCR < 99%)"
                    )
                    f_pod_max = st.number_input(
                        "📸 POD máximo (%)",
                        min_value=80.0, max_value=100.0, value=100.0, step=0.1,
                        format="%.1f",
                        help="Muestra conductores con POD ≤ este %"
                    )

                # Resumen de filtros activos
                filtros_activos = []
                if f_problemas:      filtros_activos.append(f"Problemas: {', '.join(f_problemas)}")
                if f_dnr_min > 0:    filtros_activos.append(f"DNR ≥ {f_dnr_min}")
                if f_score_max < 100: filtros_activos.append(f"Score ≤ {f_score_max}")
                if f_dcr_max < 100.0: filtros_activos.append(f"DCR ≤ {f_dcr_max:.1f}%")
                if f_pod_max < 100.0: filtros_activos.append(f"POD ≤ {f_pod_max:.1f}%")
                if filtros_activos:
                    st.info(f"🔬 Filtros avanzados activos: {' · '.join(filtros_activos)}")

            if st.button("🔍 Buscar", type="primary", use_container_width=True):
                p = "%s" if db_config['type'] == 'postgresql' else "?"

                # Semanas efectivas para JTs: intersección con permitidas
                if is_jt and allowed_hist:
                    weeks_to_use = [w for w in f_week if w in allowed_hist] if f_week else allowed_hist
                else:
                    weeks_to_use = f_week

                where_clauses = []
                params = []

                # ── Filtros básicos ────────────────────────────────────────
                if is_jt and JT_CENTRO:
                    where_clauses.append(f"centro = {p}")
                    params.append(JT_CENTRO)
                elif f_center:
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

                # ── Filtros avanzados ──────────────────────────────────────
                if f_problemas:
                    # OR entre problemas seleccionados: LIKE '%DNR%' OR LIKE '%DCR%' ...
                    prob_clauses = []
                    for prob_label in f_problemas:
                        keyword = PROBLEMAS_OPCIONES[prob_label]
                        prob_clauses.append(f"LOWER(detalles) LIKE {p}")
                        params.append(f"%{keyword.lower()}%")
                    where_clauses.append(f"({' OR '.join(prob_clauses)})")

                if f_dnr_min > 0:
                    where_clauses.append(f"dnr >= {p}")
                    params.append(float(f_dnr_min))

                if f_score_max < 100:
                    where_clauses.append(f"score <= {p}")
                    params.append(float(f_score_max))

                if f_dcr_max < 100.0:
                    where_clauses.append(f"dcr <= {p}")
                    params.append(f_dcr_max / 100.0)

                if f_pod_max < 100.0:
                    where_clauses.append(f"pod <= {p}")
                    params.append(f_pod_max / 100.0)

                where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                # ── Paginación real con LIMIT/OFFSET ──────────────────────
                PAGE_SIZE = 200
                page = st.session_state.get('hist_page', 0)

                # Contar total primero (query ligera)
                with scorecard.db_connection(db_config) as conn_count:
                    df_count = pd.read_sql_query(
                        f"SELECT COUNT(*) AS n FROM scorecards {where_sql}",
                        conn_count, params=params if params else None
                    )
                total_rows = int(df_count['n'].iloc[0]) if not df_count.empty else 0

                total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
                page = min(page, total_pages - 1)

                offset = page * PAGE_SIZE
                q = f"""
                    SELECT semana, centro, driver_name AS conductor, driver_id AS id,
                           calificacion, score, dnr, dcr, pod, cc, detalles
                    FROM scorecards {where_sql}
                    ORDER BY fecha_semana DESC, semana DESC, score DESC
                    LIMIT {PAGE_SIZE} OFFSET {offset}
                """
                with scorecard.db_connection(db_config) as conn2:
                    df_filtered = pd.read_sql_query(q, conn2, params=params if params else None)
                for _c, _p in [('dcr','dcr_pct'),('pod','pod_pct'),('cc','cc_pct')]:
                    if _c in df_filtered.columns:
                        df_filtered[_p] = (df_filtered[_c] * 100).round(2)

                st.session_state['_hist_df'] = df_filtered
                st.session_state['_hist_params']    = params
                st.session_state['_hist_where_sql'] = where_sql
                st.session_state['_hist_total_rows'] = total_rows

                if total_rows == 0:
                    st.warning("No se encontraron registros con esos filtros.")
                else:
                    # KPIs resumen
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Total registros", f"{total_rows:,}")
                    c2.metric("DNR Promedio",    f"{df_filtered['dnr'].mean():.2f}")
                    c3.metric("Score Promedio",  f"{df_filtered['score'].mean():.1f}")
                    c4.metric("DCR Promedio",    f"{df_filtered['dcr_pct'].mean():.2f}%")

                    st.divider()

                    # Paginador
                    _render_pagination(
                        'hist_page', page, total_pages, total_rows, PAGE_SIZE,
                        prev_key='hist_prev', next_key='hist_next',
                    )


                    st.dataframe(
                        df_filtered,
                        column_config={
                            "conductor":    st.column_config.TextColumn("Conductor", width="medium"),
                            "id":           st.column_config.TextColumn("ID", width="small"),
                            "calificacion": st.column_config.TextColumn("Calificación", width="small"),
                            "score":        st.column_config.NumberColumn("Score", format="%d"),
                            "dnr":          st.column_config.NumberColumn("DNR", format="%d"),
                            "dcr_pct":      st.column_config.NumberColumn("DCR%", format="%.2f"),
                            "pod_pct":      st.column_config.NumberColumn("POD%", format="%.2f"),
                            "cc_pct":       st.column_config.NumberColumn("CC%", format="%.2f"),
                            "detalles":     st.column_config.TextColumn("Detalles", width="large"),
                        },
                        use_container_width=True,
                        hide_index=True,
                        height=450,
                    )

                    # ── E) Export: página actual + export completo (admin) ─
                    dl1, dl2 = st.columns(2)
                    with dl1:
                        csv_page = df_filtered.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            f"📥 Descargar página ({len(df_filtered)} filas)",
                            csv_page, "historico_pagina.csv", "text/csv",
                            use_container_width=True
                        )
                    if is_admin:
                        with dl2:
                            if st.button("📦 Exportar todo (Power BI)", use_container_width=True,
                                         help="Descarga TODOS los registros filtrados en un CSV optimizado para Power BI"):
                                with st.spinner("Generando export completo..."):
                                    q_full = f"""
                                        SELECT semana, centro, driver_id, driver_name,
                                               calificacion, score, dnr, fs_count,
                                               dcr, pod, cc, rts, cdf, fdps, pdf_loaded,
                                               entregados_oficial, dcr_oficial, pod_oficial,
                                               lor_dpmo, dsc_dpmo, ce_dpmo,
                                               fecha_semana, uploaded_by, timestamp
                                        FROM scorecards {where_sql}
                                        ORDER BY fecha_semana DESC, semana DESC, centro, score DESC
                                    """
                                    with scorecard.db_connection(db_config) as conn_full:
                                        df_full = pd.read_sql_query(
                                            q_full, conn_full,
                                            params=params if params else None
                                        )
                                    for _c, _p in [('dcr','dcr_pct'),('pod','pod_pct'),('cc','cc_pct'),
                                                   ('rts','rts_pct'),('cdf','cdf_pct'),
                                                   ('dcr_oficial','dcr_oficial_pct'),
                                                   ('pod_oficial','pod_oficial_pct')]:
                                        if _c in df_full.columns:
                                            df_full[_p] = (df_full[_c] * 100).round(2)
                                    csv_full = df_full.to_csv(index=False).encode('utf-8')
                                    st.download_button(
                                        f"⬇️ Descargar {len(df_full):,} filas",
                                        csv_full,
                                        f"winiw_export_powerbi_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                        "text/csv",
                                        use_container_width=True
                                    )
            # ── Si no se pulsó Buscar pero hay resultados previos: redibujar ─
            elif st.session_state.get("_hist_df") is not None:
                page       = st.session_state.get("hist_page", 0)
                PAGE_SIZE  = 200
                total_rows = st.session_state.get('_hist_total_rows', 0)
                total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
                page   = min(page, total_pages - 1)
                offset = page * PAGE_SIZE

                _where_sql_cached = st.session_state.get('_hist_where_sql', '')
                _params_cached    = st.session_state.get('_hist_params', [])
                _q_page = f"""
                    SELECT semana, centro, driver_name AS conductor, driver_id AS id,
                           calificacion, score, dnr, dcr, pod, cc, detalles
                    FROM scorecards {_where_sql_cached}
                    ORDER BY fecha_semana DESC, semana DESC, score DESC
                    LIMIT {PAGE_SIZE} OFFSET {offset}
                """
                with scorecard.db_connection(db_config) as _conn_p:
                    df_page_hist = pd.read_sql_query(
                        _q_page, _conn_p,
                        params=_params_cached if _params_cached else None
                    )
                for _c, _p in [('dcr','dcr_pct'),('pod','pod_pct'),('cc','cc_pct')]:
                    if _c in df_page_hist.columns:
                        df_page_hist[_p] = (df_page_hist[_c] * 100).round(2)
                st.session_state['_hist_df'] = df_page_hist

                _ref = df_page_hist
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total", f"{total_rows:,}")
                c2.metric('DNR medio',   f"{_ref['dnr'].mean():.2f}")
                c3.metric('Score medio', f"{_ref['score'].mean():.1f}")
                c4.metric('DCR medio',   f"{(_ref['dcr_pct'].mean() if 'dcr_pct' in _ref.columns else 0):.2f}%")
                st.divider()
                _render_pagination(
                    'hist_page', page, total_pages, total_rows, PAGE_SIZE,
                    prev_key='hist_prev2', next_key='hist_next2',
                )
                st.dataframe(
                    df_page_hist,
                    column_config={
                        "conductor":    st.column_config.TextColumn("Conductor", width="medium"),
                        "id":           st.column_config.TextColumn("ID", width="small"),
                        "calificacion": st.column_config.TextColumn("Calificación", width="small"),
                        "score":        st.column_config.NumberColumn("Score", format="%d"),
                        "dnr":          st.column_config.NumberColumn("DNR", format="%d"),
                        "dcr_pct":      st.column_config.NumberColumn("DCR%", format="%.2f"),
                        "pod_pct":      st.column_config.NumberColumn("POD%", format="%.2f"),
                        "cc_pct":       st.column_config.NumberColumn("CC%", format="%.2f"),
                        "detalles":     st.column_config.TextColumn("Detalles", width="large"),
                    },
                    use_container_width=True,
                    hide_index=True,
                    height=450,
                )

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
# TAB: ADMINISTRACIÓN
# ─────────────────────────────────────────────────────────────────────────────

if tab_admin:
    with tab_admin:
        st.header("👑 Panel de Administración")

        # ── Gestión de Usuarios ───────────────────────────────────────────────
        st.subheader("👥 Gestión de Usuarios")

        # ── Tabla completa de usuarios con estado en tiempo real ──────────────
        try:
            with scorecard.db_connection(db_config) as conn:
                df_users = pd.read_sql_query(
                    """SELECT u.username, u.role, u.active, u.must_change_password,
                              la.attempt_count, la.locked_until
                       FROM users u
                       LEFT JOIN login_attempts la ON LOWER(u.username) = LOWER(la.username)
                       ORDER BY
                           CASE u.role WHEN 'superadmin' THEN 1 WHEN 'admin' THEN 2 ELSE 3 END,
                           u.username""",
                    conn
                )
        except Exception:
            df_users = pd.DataFrame()

        if not df_users.empty:
            # Construir tabla HTML con semáforos de estado
            role_badge = {
                'superadmin': ("<span style='background:#dc3545;color:white;padding:2px 8px;"
                               "border-radius:10px;font-size:0.8em'>👑 Superadmin</span>"),
                'admin':      ("<span style='background:#0d6efd;color:white;padding:2px 8px;"
                               "border-radius:10px;font-size:0.8em'>🔑 Admin</span>"),
                'jt':         ("<span style='background:#198754;color:white;padding:2px 8px;"
                               "border-radius:10px;font-size:0.8em'>👔 JT</span>"),
            }

            rows_html = []
            for i, row in enumerate(df_users.itertuples(index=False)):
                bg = '#1e2530' if i % 2 == 0 else '#262d3a'

                # Estado de la cuenta
                if not row.active:
                    status = "<span style='color:#6c757d'>⬛ Inactivo</span>"
                elif getattr(row, 'locked_until', None) is not None and pd.notna(row.locked_until):
                    try:
                        lu = datetime.strptime(str(row.locked_until)[:19], "%Y-%m-%d %H:%M:%S")
                        if datetime.now() < lu:
                            status = "<span style='color:#dc3545'>🔒 Bloqueado</span>"
                        else:
                            status = "<span style='color:#198754'>✅ Activo</span>"
                    except Exception:
                        status = "<span style='color:#198754'>✅ Activo</span>"
                else:
                    status = "<span style='color:#198754'>✅ Activo</span>"

                # Indicador de cambio de contraseña pendiente
                pwd_warn = " <span style='color:#fd7e14;font-size:0.75em'>⚠️ cambio pendiente</span>" if row.must_change_password else ""

                rows_html.append(f"""
                <tr style='background:{bg}'>
                    <td style='padding:8px 12px;font-weight:600'>{row.username}{pwd_warn}</td>
                    <td style='padding:8px 12px'>{role_badge.get(row.role, row.role)}</td>
                    <td style='padding:8px 12px'>{status}</td>
                    <td style='padding:8px 12px;text-align:center;color:{"#dc3545" if getattr(row,"attempt_count",0) and getattr(row,"attempt_count",0) > 0 else "#6c757d"}'>{int(row.attempt_count) if pd.notna(row.attempt_count) else 0}</td>
                </tr>
                """)

            _clean_user_rows = "".join(r.strip() for r in rows_html)
            st.markdown(clean_html(f"""
<div style='overflow-x:auto;border-radius:8px;border:1px solid #dee2e6;margin-bottom:1rem'>
<table style='width:100%;border-collapse:collapse;font-size:0.9em'>
<thead>
<tr style='background:#232f3e;color:white'>
<th style='padding:10px 12px;text-align:left'>Usuario</th>
<th style='padding:10px 12px;text-align:left'>Rol</th>
<th style='padding:10px 12px;text-align:left'>Estado</th>
<th style='padding:10px 12px;text-align:center'>Intentos fallidos</th>
</tr>
</thead>
<tbody>{_clean_user_rows}</tbody>
</table></div>
"""), unsafe_allow_html=True)
        else:
            st.info("No hay usuarios en la BD todavía.")

        st.markdown("---")

        # ── 4 acciones en columnas ────────────────────────────────────────────
        col_create, col_edit, col_reset, col_delete = st.columns(4)

        # ── CREAR ─────────────────────────────────────────────────────────────
        with col_create:
            st.markdown("#### ➕ Crear usuario")
            with st.form("create_user_form"):
                new_username = st.text_input("Nombre de usuario")
                new_password = st.text_input("Contraseña temporal", type="password",
                                             help="Mínimo 8 caracteres. El usuario deberá cambiarla al entrar.")
                new_password_confirm = st.text_input("Confirmar contraseña", type="password")
                if is_superadmin:
                    new_role = st.selectbox("Rol", ["jt", "admin", "superadmin"])
                else:
                    new_role = "jt"
                    st.caption("ℹ️ Los admins solo pueden crear JTs.")

                # Centro asignado (solo visible si el rol es JT)
                centros_disponibles = ["(Sin restricción)"]
                try:
                    with scorecard.db_connection(db_config) as conn_c:
                        centros_disponibles += pd.read_sql_query(
                            "SELECT DISTINCT centro FROM scorecards ORDER BY centro", conn_c
                        )['centro'].tolist()
                except Exception as _e:
                    _log.debug(f"centros_disponibles: {_e}")
                new_centro_asignado = st.selectbox(
                    "Centro asignado (solo JTs)", centros_disponibles,
                    help="Restringe al JT a ver solo este centro. 'Sin restricción' = ve todos.",
                    key="create_user_centro"
                )

                if st.form_submit_button("✅ Crear", use_container_width=True, type="primary"):
                    if not new_username.strip() or not new_password:
                        st.error("❌ Completa todos los campos")
                    elif new_password != new_password_confirm:
                        st.error("❌ Las contraseñas no coinciden")
                    elif len(new_password) < 8:
                        st.error("❌ Mínimo 8 caracteres")
                    elif new_role not in ['jt', 'admin', 'superadmin']:
                        st.error("❌ Rol inválido")
                    else:
                        try:
                            centro_val = (
                                new_centro_asignado
                                if new_role == 'jt' and new_centro_asignado != "(Sin restricción)"
                                else None
                            )
                            ph = "%s" if db_config['type'] == 'postgresql' else "?"
                            with scorecard.db_connection(db_config) as conn:
                                cursor = conn.cursor()
                                cursor.execute(
                                    f"INSERT INTO users (username, password, role, active, "
                                    f"must_change_password, centro_asignado) "
                                    f"VALUES ({ph}, {ph}, {ph}, 1, 1, {ph})",
                                    (new_username.strip(), scorecard.hash_password(new_password),
                                     new_role, centro_val)
                                )
                                conn.commit()
                            centro_info = f" → centro: {centro_val}" if centro_val else ""
                            _audit(f"Creó usuario '{new_username.strip()}' rol='{new_role}'{centro_info}")
                            st.success(f"✅ '{new_username.strip()}' creado{centro_info}")
                            cached_user_centro.clear()
                            st.rerun()  # Refresca lista de usuarios tras crear uno nuevo
                        except Exception as e:
                            if "UNIQUE" in str(e).upper() or "unique" in str(e):
                                st.error("❌ El usuario ya existe")
                            else:
                                st.error(f"❌ Error: {e}")

        # ── CAMBIAR ROL ───────────────────────────────────────────────────────
        with col_edit:
            st.markdown("#### ✏️ Cambiar rol")
            if not df_users.empty:
                # Solo superadmin puede cambiar roles de admins/superadmins
                editable = df_users[
                    (df_users['username'] != user_data_session['name']) &
                    (df_users['active'] == 1)
                ]
                if not is_superadmin:
                    editable = editable[editable['role'] == 'jt']

                with st.form("change_role_form"):
                    if not editable.empty:
                        target_edit = st.selectbox("Usuario", editable['username'].tolist(), key="edit_user_sel")
                        new_role_edit = st.selectbox(
                            "Nuevo rol",
                            ["jt", "admin"] if not is_superadmin else ["jt", "admin", "superadmin"],
                            key="edit_role_sel"
                        )
                        if st.form_submit_button("💾 Guardar", use_container_width=True):
                            try:
                                current = get_user_role(target_edit, db_config)
                                if current == 'superadmin' and not is_superadmin:
                                    st.error("🛑 Solo superadmin puede cambiar el rol de otro superadmin")
                                else:
                                    ph2 = "%s" if db_config['type'] == 'postgresql' else "?"
                                    with scorecard.db_connection(db_config) as conn:
                                        cursor = conn.cursor()
                                        cursor.execute(
                                            f"UPDATE users SET role = {ph2} WHERE username = {ph2}",
                                            (new_role_edit, target_edit)
                                        )
                                        conn.commit()
                                    _audit(f"Cambió rol de '{target_edit}': {current} → {new_role_edit}")
                                    st.success(f"✅ {target_edit}: {current} → {new_role_edit}")
                                    st.rerun()  # Refresca tabla de roles tras cambio
                            except Exception as e:
                                st.error(f"❌ Error: {e}")
                    else:
                        st.caption("No hay usuarios editables.")
                        st.form_submit_button("—", disabled=True)
            else:
                st.caption("Sin usuarios.")

        # ── RESETEAR CONTRASEÑA ───────────────────────────────────────────────
        with col_reset:
            st.markdown("#### 🔑 Resetear contraseña")
            if not df_users.empty:
                resettable = df_users[df_users['username'] != user_data_session['name']]
                if not is_superadmin:
                    resettable = resettable[resettable['role'] == 'jt']

                with st.form("reset_pw_form"):
                    if not resettable.empty:
                        target_reset = st.selectbox("Usuario", resettable['username'].tolist(), key="reset_user_sel")
                        new_pw_reset  = st.text_input("Nueva contraseña", type="password", key="reset_pw_input",
                                                      help="Mínimo 8 caracteres. El usuario deberá cambiarla al entrar.")
                        new_pw_reset2 = st.text_input("Confirmar", type="password", key="reset_pw_input2")

                        if st.form_submit_button("🔄 Resetear", use_container_width=True):
                            if not new_pw_reset:
                                st.error("❌ Introduce una contraseña")
                            elif new_pw_reset != new_pw_reset2:
                                st.error("❌ Las contraseñas no coinciden")
                            elif len(new_pw_reset) < 8:
                                st.error("❌ Mínimo 8 caracteres")
                            else:
                                try:
                                    target_role_r = get_user_role(target_reset, db_config)
                                    if target_role_r in ['admin', 'superadmin'] and not is_superadmin:
                                        st.error("🛑 Solo superadmin puede resetear contraseñas de admins")
                                    else:
                                        new_h = scorecard.hash_password(new_pw_reset)
                                        ph3 = "%s" if db_config['type'] == 'postgresql' else "?"
                                        with scorecard.db_connection(db_config) as conn:
                                            cursor = conn.cursor()
                                            cursor.execute(
                                                f"UPDATE users SET password = {ph3}, must_change_password = 1 "
                                                f"WHERE username = {ph3}",
                                                (new_h, target_reset)
                                            )
                                            conn.commit()
                                        _audit(f"Reseteó contraseña de '{target_reset}'")
                                        st.success(f"✅ Contraseña de '{target_reset}' reseteada")
                                except Exception as e:
                                    st.error(f"❌ Error: {e}")
                    else:
                        st.caption("Sin usuarios disponibles.")
                        st.form_submit_button("—", disabled=True)
            else:
                st.caption("Sin usuarios.")

        # ── ACTIVAR / DESACTIVAR / ELIMINAR ───────────────────────────────────
        with col_delete:
            st.markdown("#### 🗑️ Desactivar / Eliminar")
            if not df_users.empty:
                manageable = df_users[df_users['username'] != user_data_session['name']]
                if not is_superadmin:
                    manageable = manageable[manageable['role'] == 'jt']

                with st.form("manage_user_form"):
                    if not manageable.empty:
                        target_manage = st.selectbox("Usuario", manageable['username'].tolist(), key="manage_user_sel")
                        action = st.radio("Acción", ["Desactivar", "Reactivar", "Eliminar permanentemente"],
                                          key="manage_action")

                        col_btn1, col_btn2 = st.columns(2)
                        confirm_del = st.checkbox("Confirmar acción", key="confirm_manage")

                        if st.form_submit_button("⚡ Ejecutar", use_container_width=True,
                                                  type="primary" if action == "Eliminar permanentemente" else "secondary"):
                            if not confirm_del:
                                st.error("❌ Marca la casilla de confirmación")
                            else:
                                try:
                                    target_role_m = get_user_role(target_manage, db_config)

                                    # Guardar superadmin único
                                    if target_role_m == 'superadmin':
                                        ph4 = "%s" if db_config['type'] == 'postgresql' else "?"
                                        with scorecard.db_connection(db_config) as conn_c:
                                            cursor_c = conn_c.cursor()
                                            cursor_c.execute(
                                                f"SELECT COUNT(*) FROM users WHERE role = {ph4} AND active = 1",
                                                ('superadmin',)
                                            )
                                            total_sa = cursor_c.fetchone()[0]
                                        if total_sa <= 1 and action != "Reactivar":
                                            st.error("🛑 No puedes desactivar/eliminar al único Superadmin")
                                            st.stop()

                                    if target_role_m in ['admin', 'superadmin'] and not is_superadmin:
                                        st.error("🛑 Solo un Superadmin puede gestionar admins")
                                    else:
                                        ph5 = "%s" if db_config['type'] == 'postgresql' else "?"
                                        with scorecard.db_connection(db_config) as conn:
                                            cursor = conn.cursor()
                                            if action == "Desactivar":
                                                cursor.execute(
                                                    f"UPDATE users SET active = 0 WHERE username = {ph5}",
                                                    (target_manage,)
                                                )
                                                msg = f"'{target_manage}' desactivado"
                                            elif action == "Reactivar":
                                                cursor.execute(
                                                    f"UPDATE users SET active = 1 WHERE username = {ph5}",
                                                    (target_manage,)
                                                )
                                                msg = f"'{target_manage}' reactivado"
                                            else:  # Eliminar permanentemente
                                                cursor.execute(
                                                    f"DELETE FROM users WHERE username = {ph5}",
                                                    (target_manage,)
                                                )
                                                cursor.execute(
                                                    f"DELETE FROM login_attempts WHERE LOWER(username) = LOWER({ph5})",
                                                    (target_manage,)
                                                )
                                                msg = f"'{target_manage}' eliminado permanentemente"
                                            conn.commit()
                                        _audit(f"{action}: {msg}")
                                        st.success(f"✅ {msg}")
                                        st.rerun()  # Refresca lista tras acción admin
                                except Exception as e:
                                    st.error(f"❌ Error: {e}")
                    else:
                        st.caption("Sin usuarios gestionables.")
                        st.form_submit_button("—", disabled=True)
            else:
                st.caption("Sin usuarios.")

        st.markdown("---")

        # ── Desbloquear usuario bloqueado por rate limiting ───────────────────
        st.subheader("🔓 Desbloquear Cuentas")
        try:
            with scorecard.db_connection(db_config) as conn:
                df_locked = pd.read_sql_query(
                    "SELECT username, attempt_count, locked_until FROM login_attempts "
                    "WHERE locked_until IS NOT NULL ORDER BY locked_until DESC",
                    conn
                )

            if df_locked.empty:
                st.success("✅ No hay cuentas bloqueadas actualmente.")
            else:
                # Filtrar solo las que siguen bloqueadas — comparar datetime, no string
                now_dt = datetime.now()
                df_still_locked = df_locked[df_locked['locked_until'].apply(lambda v: _is_still_locked(v, now_dt))]

                if df_still_locked.empty:
                    st.success("✅ No hay cuentas actualmente bloqueadas.")
                else:
                    st.warning(f"⚠️ {len(df_still_locked)} cuenta(s) bloqueada(s) por intentos fallidos:")

                    for lrow in df_still_locked.itertuples(index=False):
                        try:
                            lu = datetime.strptime(str(lrow.locked_until)[:19], "%Y-%m-%d %H:%M:%S")
                            remaining_mins = max(0, int((lu - datetime.now()).total_seconds() // 60))
                        except Exception:
                            remaining_mins = "?"

                        lcol1, lcol2 = st.columns([3, 1])
                        lcol1.markdown(
                            f"🔒 **{lrow.username}** — "
                            f"{int(lrow.attempt_count)} intentos fallidos — "
                            f"se desbloquea en ~{remaining_mins} min"
                        )
                        if lcol2.button("Desbloquear", key=f"unlock_{lrow.username}", use_container_width=True):
                            try:
                                scorecard.record_login_attempt(
                                    lrow.username, success=True, db_config=db_config
                                )
                                _audit(f"Desbloqueó manualmente a '{lrow.username}'")
                                st.success(f"✅ '{lrow.username}' desbloqueado")
                                st.rerun()  # Refresca lista de bloqueados
                            except Exception as e:
                                st.error(f"❌ Error: {e}")
        except Exception as e:
            st.warning(f"No se pudo cargar el estado de bloqueos: {e}")

        # ── F) Asignación de Centro a JTs existentes ─────────────────────────
        st.markdown("---")
        st.subheader("🗺️ Centro Asignado por JT")
        st.caption(
            "Restringe a cada JT a ver solo los datos de su centro. "
            "Sin asignación, el JT puede ver todos los centros."
        )

        try:
            with scorecard.db_connection(db_config) as conn_jt:
                df_jts = pd.read_sql_query(
                    "SELECT username, centro_asignado FROM users "
                    "WHERE role = 'jt' AND active = 1 ORDER BY username",
                    conn_jt
                )

            if df_jts.empty:
                st.info("No hay usuarios JT activos.")
            else:
                # Obtener centros disponibles
                centros_asig = ["(Sin restricción)"]
                try:
                    with scorecard.db_connection(db_config) as conn_cen:
                        centros_asig += pd.read_sql_query(
                            "SELECT DISTINCT centro FROM scorecards ORDER BY centro", conn_cen
                        )['centro'].tolist()
                except Exception as _e:
                    _log.debug(f"centros_asig: {_e}")

                # Tabla de asignaciones actuales
                rows_jt = []
                for jr in df_jts.itertuples(index=False):
                    centro_actual = jr.centro_asignado or "—  (todos)"
                    badge_c = (
                        f"<span style='background:#0d6efd;color:white;padding:2px 8px;"
                        f"border-radius:10px;font-size:0.8em'>{jr.centro_asignado}</span>"
                        if jr.centro_asignado
                        else "<span style='color:#6c757d;font-size:0.85em'>Sin restricción</span>"
                    )
                    rows_jt.append(
                        f"<tr><td style='padding:8px 12px;font-weight:600'>{jr.username}</td>"
                        f"<td style='padding:8px 12px'>{badge_c}</td></tr>"
                    )

                st.markdown(f"""
                <div style='border-radius:8px;border:1px solid #dee2e6;overflow:hidden;margin-bottom:1rem'>
                <table style='width:100%;border-collapse:collapse;font-size:0.9em'>
                    <thead><tr style='background:#232f3e;color:white'>
                        <th style='padding:8px 12px;text-align:left'>JT</th>
                        <th style='padding:8px 12px;text-align:left'>Centro asignado</th>
                    </tr></thead>
                    <tbody>{''.join(rows_jt)}</tbody>
                </table></div>
                """, unsafe_allow_html=True)

                with st.form("assign_centro_form"):
                    ac1, ac2, ac3 = st.columns([2, 2, 1])
                    jt_to_assign = ac1.selectbox(
                        "JT", df_jts['username'].tolist(), key="assign_jt_sel"
                    )
                    centro_to_assign = ac2.selectbox(
                        "Centro", centros_asig, key="assign_centro_sel"
                    )
                    if st.form_submit_button("💾 Guardar asignación", use_container_width=True):
                        valor = None if centro_to_assign == "(Sin restricción)" else centro_to_assign
                        ok_ca = scorecard.set_user_centro(jt_to_assign, valor, db_config)
                        if ok_ca:
                            _clear_all_caches()
                            info = f"→ {valor}" if valor else "→ sin restricción"
                            _audit(f"Asignó centro a '{jt_to_assign}' {info}")
                            st.success(f"✅ '{jt_to_assign}' {info}")
                            st.rerun()  # Refresca asignación de centro
                        else:
                            st.error("❌ Error guardando la asignación")
        except Exception as e:
            st.warning(f"No se pudo cargar JTs: {e}")

        # ── Zona Superadmin ──────────────────────────────────────────────────
        if is_superadmin:
            st.divider()
            st.subheader("👑 Zona Superadmin")

            t1, t2, t3 = st.tabs(["📊 Estadísticas", "📝 Logs", "⚙️ Configuración"])

            with t1:
                try:
                    with scorecard.db_connection(db_config) as conn:
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
                            f"SELECT semana, MAX(timestamp) t FROM scorecards GROUP BY semana ORDER BY t DESC LIMIT {SEMANAS_RECIENTES}"
                        )
                        recent_weeks = cursor.fetchall()

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
                log_file = "logs/winiw_app.log"
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    n = st.slider("Líneas a mostrar", 20, 500, 100)
                    st.code(''.join(lines[-n:]), language='log')
                    st.download_button("📥 Descargar Logs", ''.join(lines), "winiw_app.log",
                                       use_container_width=True)
                else:
                    st.info("No hay logs disponibles aún.")

            with t3:
                st.warning("⚠️ Cambios que afectan a todo el sistema")

                # ── Test SMTP ───────────────────────────────────────────────
                st.markdown("#### 📧 Test de Alertas SMTP")
                smtp_cfg_t   = dict(st.secrets.get("smtp", {})) if hasattr(st, 'secrets') else {}
                alert_mail_t = st.secrets.get("alert_email", "") if hasattr(st, 'secrets') else ""
                if smtp_cfg_t and alert_mail_t:
                    st.caption(f"SMTP: {smtp_cfg_t.get('host','?')}:{smtp_cfg_t.get('port','?')} → {alert_mail_t}")
                    if st.button("📧 Enviar email de prueba", help="Verifica que el SMTP funciona correctamente"):
                        with st.spinner("Enviando..."):
                            ok_smtp = scorecard.send_alert_email(
                                smtp_cfg_t, alert_mail_t,
                                "[Test] Winiw Quality Scorecard — SMTP OK",
                                "<div style='font-family:Arial'><h3>✅ SMTP correcto</h3>"
                                "<p>Si recibes este email, las alertas automáticas funcionarán.</p></div>"
                            )
                        if ok_smtp:
                            st.success(f"✅ Email de prueba enviado a {alert_mail_t}")
                        else:
                            st.error("❌ Fallo SMTP. Revisa host/port/user/password en Secrets.")
                else:
                    st.info("Sin configuración SMTP. Añade [smtp] y alert_email en Secrets para activar alertas.")
                st.divider()

                with st.expander("💾 Info de Base de Datos"):
                    if db_config['type'] == 'postgresql':
                        st.success("🌐 Supabase/PostgreSQL")
                        st.code(f"Host: {db_config.get('host')}\nBD: {db_config.get('database')}")
                    else:
                        st.info("💾 SQLite (local) — en producción usa Supabase")

        st.divider()

        # ── Gestión de BD ────────────────────────────────────────────────
        st.subheader("🗄️ Gestión de Base de Datos")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown("#### 📊 Estadísticas")
            try:
                with scorecard.db_connection(db_config) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM scorecards")
                    st.metric("Total Registros", f"{cursor.fetchone()[0]:,}")
                    cursor.execute("SELECT COUNT(DISTINCT centro) FROM scorecards")
                    st.metric("Centros", cursor.fetchone()[0])
                    cursor.execute("SELECT COUNT(DISTINCT semana) FROM scorecards")
                    st.metric("Semanas almacenadas", cursor.fetchone()[0])
            except Exception as _e:
                _log.warning(f"stats BD error: {_e}")
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
            st.markdown("#### ⚙️ Mantenimiento")
            st.markdown("")

        with col4:
            st.markdown("#### ⚠️ Zona de Peligro")
            with st.expander("🗑️ Borrar TODO el historial"):
                st.error("Esta acción es IRREVERSIBLE")
                confirm = st.text_input("Escribe CONFIRMAR:")
                if st.button("BORRAR TODO", disabled=(confirm != "CONFIRMAR"),
                             type="primary", use_container_width=True):
                    if scorecard.reset_production_database(db_config):
                        # Reset total BD — invalidar toda la caché (correcto: toda la BD cambió)
                        _clear_all_caches()
                        _audit("⚠️ RESET TOTAL de base de datos")
                        st.success("✅ Base de datos limpiada")
                        st.rerun()  # Refresca UI tras reset de BD

        # (col3 contenido continúa abajo)
        with col3:
            if st.button("🧹 Ejecutar mantenimiento BD",
                         help="Normaliza semanas y elimina duplicados físicos. Puede tardar unos segundos.",
                         use_container_width=True):
                with st.spinner("Ejecutando mantenimiento..."):
                    ok, removed = scorecard.run_maintenance(db_config)
                if ok:
                    st.success(f"✅ Mantenimiento completado: {removed} duplicados eliminados.")
                    # Mantenimiento puede cambiar cualquier dato — invalidar toda la caché
                    _clear_all_caches()
                else:
                    st.error("❌ Error durante el mantenimiento. Ver logs.")

        st.divider()
        st.subheader("🗄️ Estado y Limpieza de Base de Datos")

        with st.expander("📊 Resumen de tablas en Supabase", expanded=False):
            try:
                with scorecard.db_connection(db_config) as _conn:
                    _tables_info = []
                    for _tbl, _lbl in [
                        ('scorecards',         'Scorecards (conductores CSV)'),
                        ('station_scorecards', 'Station Scorecards (PDFs)'),
                        ('wh_exceptions',      'WH Exceptions'),
                        ('center_targets',     'Center Targets'),
                        ('users',              'Usuarios'),
                    ]:
                        try:
                            _n = pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {_tbl}", _conn)['n'][0]
                        except Exception:
                            _n = '—'
                        _tables_info.append({'Tabla': _tbl, 'Descripción': _lbl, 'Filas': _n})

                    _centros_sc  = pd.read_sql_query("SELECT DISTINCT centro FROM scorecards ORDER BY centro", _conn)['centro'].tolist()
                    _centros_ss  = pd.read_sql_query("SELECT DISTINCT centro FROM station_scorecards ORDER BY centro", _conn)['centro'].tolist()
                    _centros_ct  = pd.read_sql_query("SELECT centro FROM center_targets ORDER BY centro", _conn)['centro'].tolist()

                st.dataframe(pd.DataFrame(_tables_info), use_container_width=True, hide_index=True)

                _c1, _c2, _c3 = st.columns(3)
                _c1.metric("Centros en scorecards", len(_centros_sc))
                _c2.metric("Centros en station_scorecards", len(_centros_ss))
                _c3.metric("Centros en center_targets", len(_centros_ct))

                _all_centros = sorted(set(_centros_sc) | set(_centros_ss))
                _missing     = sorted(set(_all_centros) - set(_centros_ct))
                if _missing:
                    st.warning(f"⚠️ **{len(_missing)} centros sin target configurado**: {', '.join(_missing)}")
                else:
                    st.success("✅ Todos los centros tienen targets configurados")
            except Exception as _e:
                st.error(f"Error leyendo BD: {_e}")

        if st.button("🔄 Sincronizar centros en center_targets",
                     help="Inserta con valores por defecto todos los centros que existen en scorecards o station_scorecards pero no tienen target configurado.",
                     use_container_width=True):
            try:
                with scorecard.db_connection(db_config) as _conn:
                    _sc  = pd.read_sql_query("SELECT DISTINCT centro FROM scorecards", _conn)['centro'].tolist()
                    _ss  = pd.read_sql_query("SELECT DISTINCT centro FROM station_scorecards", _conn)['centro'].tolist()
                    _ct  = pd.read_sql_query("SELECT centro FROM center_targets", _conn)['centro'].tolist()

                _to_insert = sorted((set(_sc) | set(_ss)) - set(_ct))
                if not _to_insert:
                    st.info("✅ Todos los centros ya están en center_targets — nada que hacer.")
                else:
                    _ok_count = 0
                    for _centro in _to_insert:
                        _defaults = {'centro': _centro, **scorecard.Config.DEFAULT_TARGETS}
                        if scorecard.save_center_targets(_defaults, db_config=db_config):
                            _ok_count += 1
                    _clear_all_caches()
                    _audit(f"Sincronizó {_ok_count} centros en center_targets")
                    st.success(f"✅ **{_ok_count} centros añadidos**: {', '.join(_to_insert)}")
                    st.rerun()
            except Exception as _e:
                st.error(f"❌ Error sincronizando: {_e}")

        st.divider()
        st.subheader("🎯 Configuración de Targets por Centro")
        st.caption("Define los umbrales de calidad para cada centro. Afecta al cálculo de scores.")

        try:
            with scorecard.db_connection(db_config) as conn:
                centros_bd = pd.read_sql_query(
                    "SELECT DISTINCT centro FROM scorecards ORDER BY centro", conn
                )['centro'].tolist()
        except Exception as _e:
            _log.warning(f"centros_bd error: {_e}")
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

            tc5, tc6, tc7 = st.columns(3)
            new_fdps = tc5.number_input("FDPS Min (%)", value=float(curr['target_fdps']*100),
                                         min_value=80.0, max_value=100.0, step=0.1,
                                         key="nt_fdps", help="First Delivery Point Stops (80–100%)") / 100
            new_rts  = tc6.number_input("RTS Max (%)",  value=float(curr['target_rts']*100),
                                         min_value=0.0, max_value=10.0, step=0.1,
                                         key="nt_rts",  help="Return to Station máximo (0–10%)") / 100
            new_cdf  = tc7.number_input("CDF Min (%)",  value=float(curr['target_cdf']*100),
                                         min_value=80.0, max_value=100.0, step=0.1,
                                         key="nt_cdf",  help="Customer Delivery Feedback (80–100%)") / 100

            if st.button("💾 Guardar Targets", type="primary"):
                scorecard.save_center_targets({
                    'centro': sel_target_center,
                    'target_dnr': new_dnr, 'target_dcr': new_dcr,
                    'target_pod': new_pod, 'target_cc': new_cc,
                    'target_fdps': new_fdps,
                    'target_rts': new_rts,
                    'target_cdf': new_cdf,
                }, db_config=db_config)
                cached_center_targets.clear()
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
    <span>🛡️ Winiw · Amazon DSP</span>
    <span></span>
    <span>🏆 Lideres en calidad</span>
</div>
""", unsafe_allow_html=True)
