# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.9.3] - 2026-03-13

### Fixed

- **Score Medio por Centro — etiquetas cortadas**: `_y_max` aumentado de `max+8` a `max+15` (cap 105) para que las etiquetas de texto no queden recortadas en el borde superior del gráfico con scores altos
- **Credencial hardcodeada en tests**: `test_scorecard_v39.py` ya no usa contraseña hardcodeada; lanza `EnvironmentError` si no hay variable de entorno configurada

---

## [3.9.2] - 2026-03-13

### Fixed — Bugs críticos de visualización

- **Gráficos Altair vacíos (barras invisibles)**: PostgreSQL devuelve tipos `Decimal`; Altair no los renderiza. Aplicado `pd.to_numeric(..., errors='coerce')` en Score Medio, Tendencia Semanal y Conductores POOR
- **Tendencia Semanal siempre vacía**: `GROUP BY semana ORDER BY fecha_semana` es inválido en PostgreSQL estricto cuando `fecha_semana` no está en el GROUP BY. Corregido con `MIN(fecha_semana) AS fecha_semana` en el SELECT y `ORDER BY MIN(fecha_semana)`
- **Histórico vacío**: `SELECT DISTINCT ... ORDER BY fecha_semana` con `fecha_semana` no seleccionada. Corregido con `ORDER BY semana DESC`
- **"Métricas Comparativas" mostraba HTML crudo**: `st.markdown(unsafe_allow_html=True)` no renderiza tablas HTML complejas en Streamlit ≥1.32. Cambiado a `st.html()`
- **"+nan" en columna "vs Ant."**: añadido check `math.isnan()` para mostrar "—" cuando no hay dato previo
- **Botón "Actualizar datos" en Histórico**: añadido `st.cache_data.clear()` para invalidar caché manualmente

### Changed

- **Tabs renombradas**: reflejan su función real — "Subir Archivos", "Subir PDFs", "Ver Conductores"
- **Headers simplificados**: "Resumen de Centros", "Subir Archivos", "PDFs Semanales"
- **Captions explicativos** añadidos en todos los gráficos del dashboard
- **max_chars=100/128** en campos de login para evitar payloads excesivos

### Added

- **Botón "🔄 Actualizar datos"** en pestaña Histórico para forzar refresco de caché

---

## [3.9.1] - 2026-03-12

### Fixed

- **Columna `anio` faltante en Supabase**: `ALTER TABLE station_scorecards ADD COLUMN IF NOT EXISTS anio INTEGER` + actualización del UNIQUE constraint para incluir `anio`
- **UNIQUE constraint sin `anio`**: `ON CONFLICT` fallaba en `station_scorecards` y `wh_exceptions` al existir constraints sin la nueva columna. Recreados constraints con `anio` incluido
- **Rama incorrecta en Streamlit Cloud**: Streamlit Cloud lee `main`, los pushes iban a `master`. Sincronizadas las ramas: `git merge master && git push origin main`

### Added

- Índice `(centro, timestamp DESC)` en `scorecards` para mejorar queries del dashboard ejecutivo

---

## [3.9.0] - 2026-03-04

### Fixed — Críticos (seguridad y corrupción silenciosa)

- **Credenciales hardcodeadas eliminadas** — usuario y contraseña superadmin retirados del código fuente; bootstrap ahora lee exclusivamente de variables de entorno
- **Código huérfano en import** — `success = main(); sys.exit(...)` ejecutaba en cada import; protegido con `if __name__ == "__main__"`
- **SQL Injection en vistas** — `CREATE VIEW ... WHERE centro = '{c}'` reemplazado por `psycopg2.sql.SQL` con `Identifier` y `Literal`
- **`logging.basicConfig()` doble** — eliminado del motor; centralizado en `app.py` antes del import del módulo

### Fixed — Altos (rendimiento y lógica)

- **`iterrows()` en escrituras BD** — `save_to_database`, `update_drivers_from_pdf`, `save_wh_exceptions`: N queries individuales → `execute_values` / `executemany`; 10-50× más rápido en lotes grandes
- **N+1 en `cached_executive_summary`** — 1 + 3×N queries → 2 queries constantes con `ROW_NUMBER() OVER PARTITION`
- **`session_state` desincronizado** — selector de semana/centro actualizaba variables locales sin sincronizar `st.session_state`
- **Comparación lexicográfica de semanas** — `WHERE semana < 'W07'` reemplazado por `ORDER BY MAX(timestamp) DESC LIMIT 1`
- **Rate limiting en memoria** — dict perdido en reinicios; migrado a tabla `login_attempts` en BD (durable, multi-worker)
- **`get_user_role()` sin filtro `active`** — usuarios desactivados podían ser reconocidos como superadmin

### Added — Nuevas funcionalidades

- **Columna `anio`** en `scorecards` y `wh_exceptions` — extraída automáticamente al guardar
- **`driver_name` en `wh_exceptions`** — lookup automático desde `scorecards`
- **`wh_count` en `get_station_scorecards`** — LEFT JOIN a `wh_exceptions` agrupado sin query adicional
- **Migración automática** para BDs existentes v3.7/v3.8 — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- **API pública del motor**: `check_login_locked()`, `record_login_attempt()`, `run_maintenance()`, etc.

### Tests

- Suite actualizada a **159 tests** (0 fallos, 14 skipped requieren PDF real)
- Nuevas clases: `TestSchemaV39`, `TestSaveToDatabaseV39`, `TestSaveWhExceptionsV39`, `TestStationScorecardWHCount`, `TestRegresionesV39`, `TestRateLimiting`

---

## [3.8.0] - 2026-03-02

### Fixed

- Pool PostgreSQL: eliminado `conn.close()` dentro del context manager
- Autenticación: `locked_until` usa comparación `datetime` real en lugar de comparación de strings
- Comparaciones de fecha: WoW y alertas usan columna `fecha_semana DATE` en lugar de `semana TEXT`
- Detección de archivos: DSC-Concessions separado de Concessions mediante lookahead negativo en regex

### Added

- Variables de entorno `WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS` como obligatorias
- Normalización automática de semana `W5` → `W05`
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
