# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.9.0] - 2026-03-04

### Fixed — Críticos (seguridad y corrupción silenciosa)

- **Credenciales hardcodeadas eliminadas** — usuario `pablo` y contraseña `Admin_Winiw_2026` retirados del código fuente; bootstrap superadmin ahora lee exclusivamente de `WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS`
- **Código huérfano en import** — `success = main(); sys.exit(...)` ejecutaba en cada import; protegido con `if __name__ == "__main__"`
- **SQL Injection en vistas** — `CREATE VIEW ... WHERE centro = '{c}'` reemplazado por `psycopg2.sql.SQL` con `Identifier` y `Literal`
- **`logging.basicConfig()` doble** — eliminado del motor; centralizado en `app.py` antes del import del módulo

### Fixed — Altos (rendimiento y lógica)

- **`iterrows()` en escrituras BD** — `save_to_database`, `update_drivers_from_pdf`, `save_wh_exceptions`: N queries individuales → `execute_values` (PostgreSQL) / `executemany` (SQLite); 10-50× más rápido en lotes de 200 drivers
- **N+1 en `cached_executive_summary`** — 1 + 3×N queries → 2 queries constantes con `ROW_NUMBER() OVER PARTITION`
- **`session_state` desincronizado** — selector de semana/centro actualizaba variables locales sin sincronizar `st.session_state`; añadido sync explícito al detectar cambio
- **Trend con 1 punto** — `if df_trend.empty or len(df_trend) < 1` era doble vacío; separado en dos condiciones con mensajes distintos
- **Comparación lexicográfica de semanas** — `WHERE semana < 'W07'` reemplazado por `ORDER BY MAX(timestamp) DESC LIMIT 1` para histórico correcto
- **`init_database()` redundante** — eliminadas llamadas desde `get_center_targets()` y `save_station_scorecard()`; añadido `try/finally` en ambas
- **Rate limiting en memoria** — dict `_LOGIN_ATTEMPTS` perdido en reinicios, invisible entre workers; migrado a tabla `login_attempts` en BD (durable, multi-worker)
- **`get_user_role()` sin filtro `active`** — usuarios desactivados podían ser reconocidos como superadmin en checks de permisos; añadido `AND active = 1`

### Fixed — Medios (calidad de código)

- **`locals()` antipattern** — `risk_group` inicializado a `None` antes del bloque condicional; comprobación `if risk_group is not None`
- **`import io` duplicado** — segunda aparición eliminada del cuerpo del módulo
- **Caché sidebar sin TTL** — 3 queries raw en cada re-render del sidebar → `cached_db_status()` con TTL=60s
- **Bare `except:` silenciosos** — todos convertidos a `except Exception as e: logger.debug(...)` en `read_excel_safe`, parser de fechas de nombre de archivo, `week_to_date`, `clean_database_duplicates`
- **`whc_pct` / `whc_tier` duplicados** — segunda aparición eliminada del `SELECT` de `get_station_scorecards`
- **`_LOGIN_ATTEMPTS` referencia huérfana** — bloque de feedback de login ahora lee el contador actualizado desde BD via `_rate_limit_row()`
- **18 llamadas `.clear()` individuales** — consolidadas en `_clear_all_caches()` que llama a `st.cache_data.clear()`

### Fixed — Bajos (calidad y consistencia)

- **Versión desincronizada** — docstring y `__version__` actualizados a `v3.9`
- **`st.stop()` en handler de borrar usuario** — reemplazado por `target_role = None` para no detener el render completo
- **Triple `drop_duplicates()`** — dos comprobaciones redundantes post-`process_concessions` eliminadas; guardián único al final del merge
- **`df_sorted` re-sorteado** — `top_10` y `bottom_10` extraídos con `.head()` / `.tail()` sin volver a ordenar
- **Convención de idioma** — documentada en docstring: Español para UI y logs, Inglés para nombres de funciones/variables (PEP8)

### Added — Nuevas funcionalidades v3.9

- **Columna `anio`** en `scorecards` y `wh_exceptions` — extraída automáticamente de la semana al guardar; útil para filtros de Power BI sin parsear strings
- **`driver_name` en `wh_exceptions`** — lookup automático desde `scorecards` al guardar excepciones WHC; `NULL` si el driver no tiene datos CSV
- **`wh_count` en `get_station_scorecards`** — LEFT JOIN a `wh_exceptions` agrupado; sin query adicional
- **Bug PDF corregido** — drivers en páginas `[2, 3]` (no `[2, 3, 4]`); WHC en `pages[4]` (no `pages[5]`); evita incluir filas WHC como drivers
- **API pública del motor**: `check_login_locked()`, `record_login_attempt()`, `run_maintenance()`, `update_user_password()`, `get_user_centro()`, `set_user_centro()`
- **`get_db_connection()` respeta `db_config['path']`** — permite tests con BD temporal sin tocar la BD de producción
- **Migración automática para BDs existentes** — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para `anio` (scorecards), `driver_name` y `anio` (wh_exceptions), `centro` (users)

### Tests

- Suite actualizada a **159 tests** (0 fallos, 14 skipped requieren PDF real)
- Nuevas clases: `TestSchemaV39`, `TestSaveToDatabaseV39`, `TestSaveWhExceptionsV39`, `TestStationScorecardWHCount`, `TestRegresionesV39`, `TestRateLimiting` completo

---

## [3.8.0] - 2026-03-02

### Fixed

- **C-01** Pool PostgreSQL: eliminado `conn.close()` dentro del context manager (`db_connection`)
- **C-02** Pool PostgreSQL: eliminado doble `conn.close()` en `clean_database_duplicates`
- **C-03** Autenticación: `locked_until` ahora usa comparación `datetime` real en lugar de comparación de strings
- **C-04** Comparaciones de fecha: WoW y alertas usan columna `fecha_semana DATE` en lugar de `semana TEXT`
- **C-05** Detección de archivos: DSC-Concessions separado de Concessions mediante lookahead negativo en regex
- **C-06** Pool PostgreSQL: `init_database` ahora usa `putconn()` en lugar de `close()`

### Added

- `WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS` como variables de entorno obligatorias
- Normalización automática de semana `W5` → `W05` en `save_to_database`
- Warning visible en sidebar cuando `bcrypt` no está instalado
- `Dockerfile` y `.dockerignore` para despliegue en contenedor
- `.env.example` con plantilla de variables de entorno
- CI con GitHub Actions (`tests.yml`)

---

## [3.7.0] - 2026-02

### Added

- Paginación en pestaña Scorecard (`DRIVERS_PER_PAGE = 20`)
- Trends pre-batch para eliminar consultas N+1
- 10 funciones cacheadas con TTLs granulares

---

## [3.5.0] - versión inicial documentada

### Added

- Primera versión estable con soporte SQLite (local) y PostgreSQL (producción)
- Autenticación con bcrypt y rate limiting por cuenta
- Exportación a Excel con formato profesional

---

© 2026 [@pablo25rf](https://github.com/pablo25rf)
