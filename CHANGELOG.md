# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
