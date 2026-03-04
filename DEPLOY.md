# Winiw Quality Scorecard — Guía de Deploy v3.9
## De cero a producción en Streamlit Cloud + Supabase

> Autor: [@pablo25rf](https://github.com/pablo25rf)

---

## Requisitos previos

- Cuenta en [Streamlit Cloud](https://streamlit.io/cloud) (gratuita)
- Cuenta en [Supabase](https://supabase.com) (gratuita hasta 500MB)
- Repositorio en GitHub: `github.com/pablo25rf/winiw` (o el nombre que uses)
- Python 3.10+ local para pruebas

---

## 1. Estructura de ficheros

```
winiw/
├── app.py                                        # Aplicación principal
├── amazon_scorecard_ultra_robust_v3_FINAL.py     # Motor de procesamiento v3.9
├── requirements.txt                              # Dependencias Python
├── .gitignore                                    # Excluye secrets y BD local
├── .env.example                                  # Plantilla variables de entorno
├── secrets_toml.example                          # Plantilla secrets.toml
├── test_scorecard_v39.py                         # Suite de 159 tests
├── Dockerfile
├── .dockerignore
├── instalar_windows.bat
├── instalar_linux_mac.sh
└── .streamlit/
    └── secrets.toml                              # ⚠️ NO subir a Git
```

---

## 2. requirements.txt

```txt
streamlit>=1.32.0,<2.0.0
pandas>=2.0.0,<3.0.0
numpy>=1.24.0,<2.0.0
openpyxl>=3.1.0,<4.0.0
psycopg2-binary>=2.9.0,<3.0.0
bcrypt>=4.0.0,<5.0.0
pdfplumber>=0.10.0,<1.0.0
```

> **Nota sobre psycopg2:** En Streamlit Cloud usa `psycopg2-binary`. En servidores propios con PostgreSQL compilado puedes usar `psycopg2` sin el `-binary`.

---

## 3. .gitignore

```gitignore
# Secretos — NUNCA en Git
.streamlit/secrets.toml
*.db
amazon_quality.db
.env

# Python
__pycache__/
*.pyc
venv/
.venv/

# Logs
logs/
*.log
```

---

## 4. Configurar Supabase

### 4.1 Crear el proyecto
1. Ir a [app.supabase.com](https://app.supabase.com) → **New project**
2. Nombre: `winiw-production` (o similar)
3. Región: `eu-west-1` (Europa — España)
4. Contraseña de BD: genera una fuerte y guárdala

### 4.2 Obtener credenciales
1. **Settings → Database → Connection string**
2. Selecciona **Transaction Pooler** (puerto 6543) — importante para Streamlit Cloud
3. Copia: `host`, `database`, `user`, `password`

### 4.3 Tablas — inicialización automática
No necesitas crear tablas manualmente. Al primer arranque, `init_database()` crea y migra:

| Tabla | Descripción |
|-------|-------------|
| `scorecards` | Datos por conductor (incluye `anio`, `driver_name`) |
| `users` | Usuarios del sistema (incluye `centro` para JTs) |
| `center_targets` | Objetivos de calidad por centro |
| `login_attempts` | Rate limiting persistente y multi-worker |
| `station_scorecards` | KPIs del PDF oficial DSP |
| `wh_exceptions` | Excepciones de horas (incluye `driver_name`, `anio`) |

Las migraciones son **idempotentes** — puedes arrancar sobre una BD existente de v3.7/v3.8 sin pérdida de datos.

---

## 5. Variables de entorno obligatorias

> ⚠️ Sin estas dos variables la app no arranca.

```bash
WINIW_ADMIN_USER=mi_usuario_admin
WINIW_ADMIN_PASS=mi_contraseña_segura_aqui
```

Opcionales si prefieres env vars en lugar de `secrets.toml` para Postgres:

```bash
POSTGRES_HOST=db.xxxx.supabase.co
POSTGRES_PORT=6543
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_password
```

---

## 6. Deploy en Streamlit Cloud

### 6.1 Subir el código a GitHub
```bash
git init
git add .
git commit -m "feat: Winiw Quality Scorecard v3.9"
git remote add origin https://github.com/pablo25rf/winiw.git
git push -u origin main
```

### 6.2 Conectar en Streamlit Cloud
1. [share.streamlit.io](https://share.streamlit.io) → **New app**
2. Repositorio: `pablo25rf/winiw`
3. Branch: `main`
4. Main file path: `app.py`
5. Clic en **Advanced settings** antes de Deploy

### 6.3 Configurar los Secrets
En **Advanced settings → Secrets**, pega el contenido del `secrets_toml.example` con tus credenciales reales:

```toml
[postgres]
host     = "db.xxxxxxxxxxxxxxxxxxxx.supabase.co"
port     = 6543
database = "postgres"
user     = "postgres"
password = "TU_PASSWORD_REAL"

[env]
WINIW_ADMIN_USER = "mi_admin"
WINIW_ADMIN_PASS = "mi_password_segura"
```

6. Clic en **Deploy**

---

## 7. Primer acceso

1. Abre la URL de tu app (`tu-app.streamlit.app`)
2. Login con el usuario y contraseña definidos en `WINIW_ADMIN_USER` / `WINIW_ADMIN_PASS`
3. **La app te forzará a cambiar la contraseña** en el primer acceso
4. Crea usuarios JT desde Admin → Gestión de Usuarios

---

## 8. Entorno local (desarrollo)

```bash
git clone https://github.com/pablo25rf/winiw.git
cd winiw
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edita .env con tus credenciales
streamlit run app.py
```

Sin `secrets.toml` ni variables Postgres, la app arranca con **SQLite local** automáticamente. El archivo `amazon_quality.db` se crea en el directorio raíz.

---

## 9. Tests antes de hacer push

```bash
WINIW_ADMIN_USER=test WINIW_ADMIN_PASS=test python -m unittest test_scorecard_v39 -v
```

Resultado esperado: **159 tests OK, 14 skipped** (los skipped requieren el PDF real de DMA3 — no son bloqueantes para CI).

---

## 10. Actualizar la app

```bash
# Verificar tests
python -m unittest test_scorecard_v39 -v

# Commit y push
git add -A
git commit -m "descripción del cambio"
git push

# Streamlit Cloud detecta el push y redespliega automáticamente (~1-2 min)
```

---

## 11. Solución de problemas frecuentes

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| `psycopg2 not found` | Falta en requirements.txt | Añadir `psycopg2-binary` |
| `Secrets not found` | Mal configurado en Streamlit Cloud | Verificar sección `[postgres]` en Secrets |
| Login bloqueado | Rate limiting activo en BD | Admin → Gestión de Usuarios → desbloquear |
| BD vacía tras redeploy | SQLite local no persiste entre deploys | Usar Supabase en producción |
| `bcrypt not found` | Solo aviso, no bloquea | Añadir `bcrypt` a requirements.txt |
| Timeout Supabase | Demasiadas conexiones simultáneas | Usar puerto 6543 (PgBouncer) en vez de 5432 |
| Caché no actualiza | TTL activo (5 min scorecards, 1 min sidebar) | Admin → sidebar → 🔄 Refrescar Datos |
| Columna `anio` faltante | BD antigua pre-v3.9 | Migración automática al arrancar — no hace falta nada manual |

---

## 12. Seguridad en producción

- Cambiar contraseña del superadmin en el primer acceso
- `bcrypt` recomendado para hashes seguros — si no está, degrada a SHA-256
- Rotar credenciales de Supabase periódicamente: Settings → Database
- Revisar logs: Admin → Zona Superadmin → descargar `winiw_app.log`
- Los JTs solo pueden ver sus semanas más recientes y su centro asignado

---

## 13. Docker

```bash
# Build
docker build -t winiw-scorecard .

# Run con variables de entorno
docker run -p 8501:8501 \
  -e WINIW_ADMIN_USER=admin \
  -e WINIW_ADMIN_PASS=password_segura \
  winiw-scorecard

# O usando un .env file
docker run -p 8501:8501 --env-file .env winiw-scorecard
```

---

*Winiw Quality Scorecard v3.9 · [@pablo25rf](https://github.com/pablo25rf) · Marzo 2026*
