# Winiw Quality Scorecard — Guía de Deploy
## De cero a producción en Streamlit Cloud + Supabase

---

## Requisitos previos

- Cuenta en [Streamlit Cloud](https://streamlit.io/cloud) (gratuita)
- Cuenta en [Supabase](https://supabase.com) (gratuita hasta 500MB)
- Repositorio Git (GitHub, GitLab o Bitbucket)
- Python 3.10+ local para pruebas

---

## 1. Estructura de ficheros

```
winiw/
├── app.py                                        # Aplicación principal
├── amazon_scorecard_ultra_robust_v3_FINAL.py     # Motor de procesamiento
├── requirements.txt                              # Dependencias Python
├── .gitignore                                    # Excluye secrets y BD local
├── secrets.toml.example                          # Plantilla de configuración
├── test_scorecard_v37.py                         # Tests del motor
└── .streamlit/
    └── secrets.toml                              # ⚠️ NO subir a Git
```

---

## 2. requirements.txt

```txt
streamlit>=1.32.0
pandas>=2.0.0
numpy>=1.24.0
openpyxl>=3.1.0
psycopg2-binary>=2.9.0
bcrypt>=4.0.0
pdfplumber>=0.10.0
```

> **Nota sobre psycopg2:** En Streamlit Cloud usa `psycopg2-binary`. En servidores propios con PostgreSQL compilado puedes usar `psycopg2` sin el `-binary`.

---

## 3. .gitignore

```gitignore
# Secretos — NUNCA en Git
.streamlit/secrets.toml
*.db
amazon_quality.db

# Python
__pycache__/
*.pyc
.env
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
3. Región: la más cercana a tus usuarios (ej: `eu-west-1` para España)
4. Contraseña de BD: genera una fuerte y guárdala

### 4.2 Obtener credenciales
1. **Settings → Database → Connection string**
2. Selecciona **Transaction Pooler** (puerto 6543)
3. Copia: `host`, `database`, `user`, `password`

### 4.3 La app inicializa las tablas automáticamente
No necesitas crear tablas manualmente. Al primer arranque, `init_database()` crea:
- `scorecards` — datos de conductores
- `users` — usuarios del sistema
- `center_targets` — objetivos por centro
- `login_attempts` — rate limiting de login
- `station_scorecards` — datos del PDF oficial
- `wh_exceptions` — excepciones de horas de trabajo

Y crea el usuario superadmin inicial usando las variables de entorno `WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS`.

> ⚠️ **Ambas variables son OBLIGATORIAS.** Si no están definidas, la aplicación lanzará un `RuntimeError` en el primer arranque y no iniciará. No existe valor por defecto — esto es intencionado por seguridad.

---

## 5. Deploy en Streamlit Cloud

### 5.1 Subir el código a GitHub
```bash
git init
git add app.py amazon_scorecard_ultra_robust_v3_FINAL.py requirements.txt .gitignore secrets.toml.example
git commit -m "Initial deploy"
git remote add origin https://github.com/TU_USUARIO/winiw.git
git push -u origin main
```

### 5.2 Conectar en Streamlit Cloud
1. [share.streamlit.io](https://share.streamlit.io) → **New app**
2. Repositorio: `TU_USUARIO/winiw`
3. Branch: `main`
4. Main file path: `app.py`
5. Clic en **Advanced settings** antes de Deploy

### 5.3 Configurar los Secrets
En **Advanced settings → Secrets**, pega el contenido de `secrets.toml.example` con tus credenciales reales:

```toml
[postgres]
host     = "db.xxxxxxxxxxxxxxxxxxxx.supabase.co"
port     = 6543
database = "postgres"
user     = "postgres"
password = "TU_PASSWORD_REAL"
```

6. Clic en **Deploy**

---

## 6. Primer acceso

1. Asegúrate de haber definido `WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS` antes de arrancar (ver sección 12)
2. Abre la URL de tu app (`tu-app.streamlit.app`)
3. Login con el usuario y contraseña definidos en esas variables
4. **La app te forzará a cambiar la contraseña** (flag `must_change_password=1`)
5. Crea los usuarios JT desde el panel Admin → Gestión de Usuarios

---

## 7. Entorno local (desarrollo)

```bash
# Clonar el repo
git clone https://github.com/TU_USUARIO/winiw.git
cd winiw

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar (usa SQLite automáticamente, sin Supabase)
streamlit run app.py
```

El archivo `amazon_quality.db` se crea automáticamente en el directorio raíz.

---

## 8. Tests

```bash
# Desde el directorio del proyecto
python -m pytest test_scorecard_v37.py -v

# O directamente con unittest
python -m unittest test_scorecard_v37 -v
```

Los tests usan SQLite en directorios temporales — no tocan la BD de producción.

---

## 9. Actualizar la app

```bash
# Hacer los cambios en local
# ...

# Verificar que los tests pasan
python -m pytest test_scorecard_v37.py -v

# Subir cambios
git add -A
git commit -m "descripción del cambio"
git push

# Streamlit Cloud detecta el push y redespliega automáticamente (~1-2 min)
```

---

## 10. Solución de problemas frecuentes

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| `psycopg2 not found` | Falta en requirements.txt | Añadir `psycopg2-binary` |
| `Secrets not found` | Mal configurado en Streamlit Cloud | Verificar sección `[postgres]` en Secrets |
| Login bloqueado | Rate limiting activo | Admin → desbloquear cuenta manualmente |
| BD vacía tras redeploy | SQLite local (no persiste) | Usar Supabase en producción |
| `bcrypt not found` | Solo avisa, no bloquea | Añadir `bcrypt` a requirements.txt para mejor seguridad |
| Timeout en Supabase | Demasiadas conexiones | Usar puerto 6543 (PgBouncer) en vez de 5432 |
| Caché no actualiza | TTL de 5 min activo | Admin → sidebar → 🔄 Refrescar Datos |

---

## 11. Seguridad en producción

- **Cambiar contraseña por defecto** del superadmin en el primer acceso (configura `WINIW_ADMIN_PASS` como variable de entorno para evitar la contraseña por defecto)
- **Habilitar bcrypt** añadiendo `bcrypt` a requirements.txt (actualmente usa SHA-256 si no está disponible)
- **Rotar credenciales** de Supabase periódicamente desde Settings → Database
- **Revisar los logs** desde Admin → Zona Superadmin → Logs (o descarga `winiw_app.log`)
- Los **JTs solo pueden ver sus semanas** más recientes y (opcionalmente) su centro asignado

---

## 12. Variables de entorno — OBLIGATORIAS en el primer arranque

`WINIW_ADMIN_USER` y `WINIW_ADMIN_PASS` son **requeridas**. Si no están definidas, la aplicación lanza un `RuntimeError` y no inicia.

```bash
# ⚠️ OBLIGATORIAS — sin estas variables la app no arranca
export WINIW_ADMIN_USER="mi_usuario_admin"
export WINIW_ADMIN_PASS="mi_contraseña_segura_aqui"

# Opcionales — solo si prefieres env vars en lugar de secrets.toml para Postgres
export POSTGRES_HOST="db.xxxx.supabase.co"
export POSTGRES_PORT=6543
export POSTGRES_DB="postgres"
export POSTGRES_USER="postgres"
export POSTGRES_PASSWORD="tu_password"
```

En **Streamlit Cloud**, define estas variables en **Advanced settings → Secrets** o como variables de entorno en el panel del proyecto. Y adapta `get_db_config()` en `app.py` para leer `os.environ` si no usas `secrets.toml`.

---

*Winiw Quality Scorecard v3.7 · Amazon DSP · Febrero 2026*
