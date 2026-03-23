# 📘 Documentación Técnica IT — Quality Scorecard v3.9

**Versión:** 3.9  
**Fecha:** Marzo 2026  
**Audiencia:** IT / DevOps  
**Autor:** [@pablo25rf](https://github.com/pablo25rf)

---

## Índice

1. [Descripción general](#1-descripción-general)
2. [Arquitectura técnica](#2-arquitectura-técnica)
3. [Stack tecnológico](#3-stack-tecnológico)
4. [Base de datos](#4-base-de-datos)
5. [Seguridad](#5-seguridad)
6. [Flujo de datos](#6-flujo-de-datos)
7. [Módulos y componentes](#7-módulos-y-componentes)
8. [API pública del motor (v3.9)](#8-api-pública-del-motor)
9. [Instalación y despliegue](#9-instalación-y-despliegue)
10. [Mantenimiento y monitoreo](#10-mantenimiento-y-monitoreo)
11. [Troubleshooting](#11-troubleshooting)
12. [Rendimiento y escalabilidad](#12-rendimiento-y-escalabilidad)

---

## 1. Descripción general

**Quality Scorecard** automatiza el procesamiento semanal de métricas de calidad de conductores Logística. Procesa hasta 7 fuentes de datos heterogéneas (CSV, Excel, HTML, PDF), calcula scores ponderados por conductor y publica los resultados en una interfaz web multi-rol.

### Reducción de carga operativa

| Concepto | Antes | Con sistema |
|----------|-------|-------------|
| Tiempo de procesamiento semanal | ~4 horas / centro | ~5 minutos |
| Fuentes de datos a consolidar | 5-7 archivos manuales | Carga automática |
| Cálculo de scores | Manual, propenso a errores | Motor determinista validado |
| Histórico | Excel locales sin estructura | BD centralizada con migraciones |

---

## 2. Arquitectura técnica

```
┌──────────────────────────────────────────────────────────┐
│                    CLIENTE (Navegador)                    │
│                  Streamlit WebSocket                      │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                    app.py (UI Layer)                      │
│  • Autenticación y sesión                                 │
│  • Caché con TTL (st.cache_data)                          │
│  • 7 pestañas según rol                                   │
│  • Rate limiting en BD (tabla login_attempts)             │
└────────────────────────┬─────────────────────────────────┘
                         │ llama a
┌────────────────────────▼─────────────────────────────────┐
│   amazon_scorecard_ultra_robust_v3_FINAL.py (Motor)      │
│  • Parsers CSV/Excel/HTML/PDF                             │
│  • Motor de scoring (calculate_score_v3_robust)           │
│  • ORM ligero: save_to_database, get_*, init_database     │
│  • API pública: check_login_locked, run_maintenance, …    │
└────────────────────────┬─────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
┌───────▼───────┐                ┌────────▼────────┐
│  PostgreSQL   │                │  SQLite          │
│  (Supabase)   │                │  (desarrollo)    │
│  producción   │                │  amazon_quality  │
│               │                │  .db             │
└───────────────┘                └──────────────────┘
```

---

## 3. Stack tecnológico

| Componente | Tecnología | Versión |
|-----------|-----------|---------|
| Interfaz web | Streamlit | ≥ 1.32 |
| Lenguaje | Python | ≥ 3.10 |
| Análisis de datos | pandas | ≥ 2.0 |
| Hojas de cálculo | openpyxl | ≥ 3.1 |
| BD producción | PostgreSQL vía psycopg2-binary | ≥ 2.9 |
| BD desarrollo | SQLite3 | stdlib |
| Hash de contraseñas | bcrypt | ≥ 4.0 (fallback: SHA-256) |
| Parseo de PDF | pdfplumber | ≥ 0.10 |

---

## 4. Base de datos

### Esquema v3.9

```sql
-- Datos de conductores
CREATE TABLE scorecards (
    id              SERIAL PRIMARY KEY,  -- INTEGER AUTOINCREMENT en SQLite
    semana          VARCHAR(10) NOT NULL,
    anio            INTEGER,             -- v3.9: extraído automáticamente de semana
    fecha_semana    DATE,
    centro          VARCHAR(20) NOT NULL,
    driver_id       VARCHAR(50) NOT NULL,
    driver_name     VARCHAR(255),
    calificacion    VARCHAR(50),
    score           DOUBLE PRECISION,
    entregados      DOUBLE PRECISION,
    dnr             DOUBLE PRECISION,
    fs_count        DOUBLE PRECISION,
    dnr_risk_events DOUBLE PRECISION,
    dcr             DOUBLE PRECISION,
    pod             DOUBLE PRECISION,
    cc              DOUBLE PRECISION,
    fdps            DOUBLE PRECISION,
    rts             DOUBLE PRECISION,
    cdf             DOUBLE PRECISION,
    -- Columnas del PDF oficial (v3.2+)
    entregados_oficial DOUBLE PRECISION,
    dcr_oficial     DOUBLE PRECISION,
    pod_oficial     DOUBLE PRECISION,
    cc_oficial      DOUBLE PRECISION,
    cdf_dpmo_oficial DOUBLE PRECISION,
    dsc_dpmo        DOUBLE PRECISION,
    lor_dpmo        DOUBLE PRECISION,
    ce_dpmo         DOUBLE PRECISION,
    pdf_loaded      INTEGER DEFAULT 0,
    detalles        TEXT,
    uploaded_by     VARCHAR(100),
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(semana, centro, driver_id)
);

-- Usuarios del sistema
CREATE TABLE users (
    id                   SERIAL PRIMARY KEY,
    username             VARCHAR(100) UNIQUE,
    password             TEXT,           -- bcrypt o sha256:hash
    role                 VARCHAR(20),    -- superadmin | admin | jt
    active               INTEGER DEFAULT 1,
    must_change_password INTEGER DEFAULT 0,
    centro               VARCHAR(20)     -- v3.9: asignación de centro para JTs
);

-- KPIs de estación (del PDF oficial Amazon)
CREATE TABLE station_scorecards (
    id              SERIAL PRIMARY KEY,
    semana          VARCHAR(10),
    centro          VARCHAR(20),
    overall_score   DOUBLE PRECISION,
    overall_standing VARCHAR(20),
    rank_station    INTEGER,
    rank_wow        INTEGER,
    -- métricas WHC, DCR, DNR, LoR, DSC, POD, CC, CE, CDF,
    -- speeding, mentor, VSA, capacity, FICO...
    focus_area_1    TEXT,
    focus_area_2    TEXT,
    focus_area_3    TEXT,
    uploaded_by     VARCHAR(100),
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(semana, centro)
);

-- Excepciones de horas de trabajo
CREATE TABLE wh_exceptions (
    id                   SERIAL PRIMARY KEY,
    semana               VARCHAR(10) NOT NULL,
    anio                 INTEGER,        -- v3.9
    fecha_semana         DATE,
    centro               VARCHAR(20) NOT NULL,
    driver_id            VARCHAR(50) NOT NULL,
    driver_name          VARCHAR(255),   -- v3.9: lookup desde scorecards
    daily_limit_exceeded  INTEGER DEFAULT 0,
    weekly_limit_exceeded INTEGER DEFAULT 0,
    under_offwork_limit   INTEGER DEFAULT 0,
    workday_limit_exceeded INTEGER DEFAULT 0,
    uploaded_by          VARCHAR(100),
    timestamp            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(semana, centro, driver_id)
);

-- Objetivos de calidad por centro
CREATE TABLE center_targets (
    id       SERIAL PRIMARY KEY,
    centro   VARCHAR(20) NOT NULL UNIQUE,
    targets  TEXT  -- JSON serializado
);

-- Rate limiting (v3.5+) — persistente y multi-worker
CREATE TABLE login_attempts (
    id           SERIAL PRIMARY KEY,
    username     VARCHAR(150) NOT NULL UNIQUE,
    fail_count   INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,
    last_attempt TIMESTAMP
);
```

### Índices clave (PostgreSQL)

```sql
CREATE INDEX idx_centro_semana ON scorecards (centro, semana);
CREATE INDEX idx_bi_query      ON scorecards (centro, semana, fecha_semana)
    INCLUDE (score, dnr, dcr, calificacion);
CREATE INDEX idx_driver_id     ON scorecards (driver_id);
CREATE INDEX idx_driver_name   ON scorecards (LOWER(driver_name));
CREATE INDEX idx_ranking       ON scorecards (centro, semana, score DESC);
CREATE INDEX idx_dnr_alto      ON scorecards (centro, semana, dnr) WHERE dnr > 5;
CREATE INDEX idx_poor_fair     ON scorecards (centro, semana, score) WHERE score < 70;
```

### Migraciones automáticas

`init_database()` es completamente **idempotente**. Cada vez que se llama (al arrancar la app) detecta las columnas existentes y añade solo las que faltan con `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. No toca datos existentes.

Columnas añadidas en migraciones anteriores que `init_database()` gestiona automáticamente:

| Columna | Tabla | Versión |
|---------|-------|---------|
| `entregados_oficial`, `dcr_oficial`, `pod_oficial`, `cc_oficial`, `cdf_dpmo_oficial`, `dsc_dpmo`, `lor_dpmo`, `ce_dpmo`, `pdf_loaded` | `scorecards` | v3.2 |
| `anio` | `scorecards` | v3.9 |
| `driver_name`, `anio` | `wh_exceptions` | v3.9 |
| `centro` | `users` | v3.9 |

---

## 5. Seguridad

### Autenticación

- Hash con **bcrypt** (salt automático, coste 12) si `bcrypt` está instalado; SHA-256 con prefijo `sha256:` como fallback
- Rate limiting: 5 intentos fallidos → 15 min de bloqueo
- Rate limiting **persistente en BD** (`login_attempts`) desde v3.5 — no se pierde en reinicios ni entre workers de Streamlit

### Autorización

- 3 roles jerárquicos: `superadmin > admin > jt`
- Las rutas de la app comprueban el rol en cada render
- `get_user_role()` filtra `active = 1` (bug de v3.8 corregido en v3.9 — usuarios desactivados ya no se reconocen como superadmin)

### SQL Injection

- Todas las queries con entrada de usuario usan parámetros (`%s` / `?`)
- Las vistas SQL con nombres de centro usan `psycopg2.sql.SQL` con `Identifier` y `Literal`
- No hay interpolación de strings en queries

### Credenciales

- **Cero credenciales hardcodeadas en el código** (corregido en v3.5)
- Bootstrap del superadmin lee exclusivamente de `WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS`
- Las contraseñas nunca se loguean

---

## 6. Flujo de datos

```
Archivos CSV/Excel/HTML
        │
        ▼
process_concessions() → DNR, Entregados
process_quality()     → DCR, POD, CC
process_false_scan()  → FS_Count
process_dwc()         → DNR_RISK_EVENTS, CC_DWC, IADC
process_fdps()        → FDPS
process_daily_report()→ datos diarios agregados
        │
        ▼
merge_data_smart()     → DataFrame unificado por driver_id
        │
        ▼
calculate_score_v3_robust() (por fila, vectorizado con apply)
        │
        ├── SCORE (0-100) + CALIFICACION + DETALLES
        │
        ▼
save_to_database()     → executemany (1 round-trip para N drivers)
        │
        ▼
PostgreSQL/SQLite: tabla scorecards
        │
        ▼
cached_* functions     → st.cache_data TTL 300s
        │
        ▼
Streamlit UI           → scorecard, dashboard, histórico
```

```
PDF oficial Amazon
        │
        ▼
parse_dsp_scorecard_pdf()
    ├── Página 1-2: métricas de estación (score, standing, rank, WHC, FICO…)
    ├── Páginas 3-4: tabla de drivers (driver_id, métricas_oficial)
    └── Página 5: Working Hours Exceptions
        │
        ▼
save_station_scorecard()  → tabla station_scorecards
save_wh_exceptions()      → tabla wh_exceptions (con driver_name lookup)
update_drivers_from_pdf() → actualiza dcr_oficial, pod_oficial… en scorecards
```

---

## 7. Módulos y componentes

### `amazon_scorecard_ultra_robust_v3_FINAL.py` — Motor

| Función / clase | Descripción |
|----------------|-------------|
| `Config` | Constantes del sistema (targets, regex, límites) |
| `init_database(db_config)` | Crea tablas y aplica migraciones idempotentes |
| `get_db_connection(db_config)` | Abre conexión PostgreSQL o SQLite según config |
| `process_concessions(df)` | Parsea concessions CSV/Excel; deduplicación interna |
| `process_quality(df)` | Parsea quality overview |
| `process_false_scan(df)` | Parsea false scan HTML |
| `process_dwc(df)` | Parsea DWC/IADC (formato antiguo y nuevo) |
| `process_fdps(df)` | Parsea FDPS |
| `process_daily_report(df)` | Parsea daily report HTML |
| `merge_data_smart(...)` | Merge de todas las fuentes con left join por driver_id |
| `calculate_score_v3_robust(row, targets)` | Score ponderado para una fila → 🌟 FANTASTIC+ (≥93) · 💎 FANTASTIC (≥90) · 🥇 GREAT (≥80) · ⚠️ FAIR (≥60) · 🛑 POOR (<60) |
| `save_to_database(df, week, center, ...)` | Upsert masivo con executemany |
| `parse_dsp_scorecard_pdf(pdf_bytes)` | Parseo completo del PDF oficial Amazon |
| `save_station_scorecard(station_data, ...)` | Guarda KPIs de estación |
| `save_wh_exceptions(wh_df, ...)` | Guarda excepciones WHC con lookup de driver_name |
| `get_station_scorecards(db_config)` | SELECT con LEFT JOIN wh_count |
| `clean_database_duplicates(db_config)` | Normaliza semanas y elimina duplicados físicos |
| `check_login_locked(username, db_config)` | Comprueba bloqueo de cuenta → (bool, segundos) |
| `record_login_attempt(username, success, ...)` | Registra intento; bloquea si supera max_attempts |
| `run_maintenance(db_config)` | Alias de `clean_database_duplicates` |
| `update_user_password(username, new_hash, ...)` | Actualiza hash y limpia must_change_password |
| `get_user_centro(username, ...)` | Lee centro asignado de un JT |
| `set_user_centro(username, centro, ...)` | Asigna o borra el centro de un JT |

### `app.py` — Interfaz Streamlit

| Función | Descripción |
|---------|-------------|
| `cached_db_status(...)` | Estado del sidebar — TTL 60 s |
| `cached_scorecard(...)` | Datos de scorecard — TTL 300 s |
| `cached_available_batches(...)` | Lotes disponibles — TTL 300 s |
| `cached_executive_summary(...)` | Dashboard ejecutivo — TTL 300 s (2 queries totales, O(1) respecto a centros) |
| `cached_driver_trend(...)` | Tendencia de conductor — TTL 300 s |
| `cached_meta(...)` | Metadatos — TTL 300 s |
| `_clear_all_caches()` | Invalida toda la caché (`st.cache_data.clear()`) |
| `check_login()` | Guard de autenticación |
| `check_session_timeout()` | Caduca la sesión por inactividad |
| `_is_locked(uname)` | Lee bloqueo desde BD |
| `_register_failed_attempt(uname)` | UPSERT en login_attempts |
| `_clear_attempts(uname)` | DELETE en login_attempts tras login exitoso |

---

## 8. API pública del motor (v3.9)

Funciones pensadas para ser llamadas desde tests, scripts externos o la propia app:

```python
import amazon_scorecard_ultra_robust_v3_FINAL as sc

db = {'type': 'sqlite', 'path': '/ruta/mi.db'}

# Inicializar BD (idempotente)
sc.init_database(db)

# Comprobar si una cuenta está bloqueada
bloqueada, segundos = sc.check_login_locked('juan', db)

# Registrar intento fallido
sc.record_login_attempt('juan', success=False, db_config=db)

# Mantenimiento — normalizar semanas y eliminar duplicados
ok, n_afectados = sc.run_maintenance(db)

# Actualizar contraseña
sc.update_user_password('juan', sc.hash_password('nueva'), db)

# Centro asignado a un JT
sc.set_user_centro('juan', 'DIC1', db)
centro = sc.get_user_centro('juan', db)  # → 'DIC1'

# Estaciones con wh_count
df_estaciones = sc.get_station_scorecards(db)
# df_estaciones tiene columna wh_count (LEFT JOIN automático)
```

---

## 9. Instalación y despliegue

Ver [DEPLOY.md](DEPLOY.md) para la guía paso a paso.

### Resumen rápido

```bash
# Clonar
git clone https://github.com/pablo25rf/winiw.git
cd winiw

# Entorno virtual
python -m venv .venv && source .venv/bin/activate

# Dependencias
pip install -r requirements.txt

# Variables obligatorias
export WINIW_ADMIN_USER=admin
export WINIW_ADMIN_PASS=password_segura

# Arrancar
streamlit run app.py
```

### CI/CD

El repositorio incluye `.github/workflows/tests.yml` que ejecuta la suite completa en cada push y pull request:

```yaml
- name: Run tests
  env:
    WINIW_ADMIN_USER: test_admin
    WINIW_ADMIN_PASS: Test_Pass_Seguro_2024!
  run: python -m unittest test_scorecard_v39 -v
```

---

## 10. Mantenimiento y monitoreo

### Logs

```bash
# Ver logs en tiempo real
tail -f winiw_app.log

# Buscar errores
grep ERROR winiw_app.log

# Los últimos 100
tail -100 winiw_app.log
```

Desde la app: **Administración → Zona Superadmin → Ver Logs**.

### Backup de SQLite (local)

```bash
cp amazon_quality.db amazon_quality_backup_$(date +%Y%m%d_%H%M).db
```

### Mantenimiento de BD desde Python

```python
import amazon_scorecard_ultra_robust_v3_FINAL as sc
db = {'type': 'sqlite', 'path': 'amazon_quality.db'}
ok, n = sc.run_maintenance(db)
print(f"Mantenimiento OK: {n} registros afectados")
```

### Supabase — monitoreo

- Dashboard: `app.supabase.com → Tu proyecto → Database → Monitoring`
- Límite plan gratuito: 500 MB, 50.000 conexiones/mes
- Puerto recomendado: **6543** (PgBouncer, pooled connections)

---

## 11. Troubleshooting

### `OperationalError: no such table: scorecards`

`init_database()` no se ha ejecutado para esta BD. Llama a `sc.init_database(db_config)` antes de cualquier otra operación.

### La BD de tests y la de producción son la misma

`get_db_connection()` respeta `db_config['path']` desde v3.9. Si no se pasa `path`, usa el archivo por defecto `amazon_quality.db`. Los tests siempre crean una BD temporal con `tempfile.mktemp()`.

### Rate limiting no funciona en multi-worker

Asegúrate de usar PostgreSQL/Supabase en producción. Con SQLite la concurrencia de escritura puede generar locks; en PostgreSQL es totalmente seguro.

### Score difiere entre CSV y PDF

El motor CSV calcula con los datos brutos de los archivos semanales. El PDF oficial de Amazon puede incluir datos de semanas parciales o con correcciones. Ambas fuentes se guardan en columnas separadas (`score` vs `dcr_oficial`, `pod_oficial`, etc.).

### `psycopg2.OperationalError: connection refused`

Verifica que el host en `secrets.toml` usa puerto **6543** (PgBouncer) y no 5432. Streamlit Cloud tiene restricciones de puertos.

---

## 12. Rendimiento y escalabilidad

### Optimizaciones v3.9

| Antes | Después |
|-------|---------|
| `iterrows()` → N queries individuales al guardar | `executemany` → 1 round-trip por lote |
| Dashboard ejecutivo: 1 + 3×N queries | 2 queries constantes (ROW_NUMBER OVER PARTITION) |
| 3 queries sin caché en cada render del sidebar | `cached_db_status` TTL=60 s |
| 18 llamadas `.clear()` individuales | `_clear_all_caches()` centralizado |
| Rate limiting en dict Python en memoria | Tabla `login_attempts` en BD |

### Tiempos de referencia (DMA3, ~100 drivers)

| Operación | Tiempo típico |
|-----------|--------------|
| Procesamiento CSV completo | 2-4 s |
| `save_to_database` (100 drivers) | < 50 ms |
| Dashboard ejecutivo (5 centros, caché fría) | 300-800 ms |
| Dashboard ejecutivo (caché caliente) | < 10 ms |
| Parseo PDF oficial | 1-3 s |

### Límites conocidos de Supabase (plan gratuito)

- 500 MB de almacenamiento
- 50.000 peticiones activas / mes
- 2 CPUs compartidas
- Para cargas mayores, considerar el plan Pro (8 GB, CPUs dedicadas)

---

*Quality Scorecard v3.9 · [@pablo25rf](https://github.com/pablo25rf) · Marzo 2026*
