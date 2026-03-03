# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.9.0] - 2026-03-03

### Changed — Rendimiento y arquitectura (app.py)

- **`_clear_all_caches()`** — función centralizada que reemplaza 5 bloques de 7-8 líneas `.clear()` duplicadas; 30+ líneas → 6 llamadas únicas
- **Helpers a nivel módulo** — `_score_color`, `_fmt_pct`, `_fmt_num`, `_diff_badge`, `_metric_row`, `_get_mini_trend`, `_is_still_locked` movidas fuera de condicionales donde se redefinían en cada render
- **`_render_pagination()`** — función única para paginación; 3 implementaciones duplicadas colapsadas en 3 llamadas
- **`_mini_trend_map`** — dict precalculado fuera del loop de conductores; `_get_mini_trend()` se llama O(n) una vez en vez de O(n) por conductor en pantalla
- **`iterrows()` → `itertuples()`** en 5 loops: `df_exec` (×2), `df_users`, `df_still_locked`, `df_jts` (4–10× más rápido)
- **`SCORE_FANTASTIC/GREAT/FAIR`** — constantes de módulo para umbrales de score; `>= 90/80/60` hardcodeados en 7 sitios → 0

### Changed — UX

- **Tab PDF DSP Scorecard** rediseñado: parseo único de todos los PDFs → tabla resumen → un solo botón "💾 Guardar N PDFs"; expanders cerrados por defecto; caché de sesión evita reparsear si no cambian los archivos
- **Filtros de calificación** reemplazados: 5 botones manuales con `st.session_state` + `st.rerun()` → `st.radio(horizontal=True)`; sin reruns forzados, sin acumulación de claves en session_state
- **Año en título PDF** — el scorecard DSP muestra `DMA3 — W14/2026` en lugar de solo `DMA3 — W14`

### Fixed

- Claves `cal_filter_X_Y`, `page_X_Y`, `{fk}_prev` acumulándose en session_state indefinidamente → eliminadas al migrar a `st.radio`
- `st.rerun()` redundante en 5 botones de filtro de calificación eliminado

### Added

- `MANUAL_OPERACION_DETALLADO.md` — manual completo de 365 líneas (el archivo anterior era un error HTTP)

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

- `WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS` como variables de entorno obligatorias; la app lanza `RuntimeError` si no están definidas al arrancar
- Normalización automática de semana `W5` → `W05` en `save_to_database`
- Warning visible en sidebar cuando `bcrypt` no está instalado (degrada a SHA-256)
- 6 tests nuevos para `update_user_password`
- Caché selectiva: reemplazados `st.cache_data.clear()` globales por invalidación por función
- `Dockerfile` y `.dockerignore` para despliegue en contenedor
- `.env.example` con plantilla de variables de entorno
- CI con GitHub Actions (`tests.yml`): suite completa en cada push y pull request

### Changed

- `ORDER BY` usa `fecha_semana DATE` en 7 queries críticas (antes ordenaba lexicográficamente por string)
- `DEFAULT_TARGETS` centralizado en `Config` como fuente única de verdad
- `DEPLOY.md`, instaladores y scripts de configuración anonimizados
- `requirements.txt` con upper bounds en todas las dependencias

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
