# Quality Scorecard — Guía de Deploy
## De cero a producción en Streamlit Cloud + Supabase

> Autor: [@pablo25rf](https://github.com/pablo25rf)

---

## Requisitos previos

- Cuenta en [Streamlit Cloud](https://streamlit.io/cloud) (gratuita)
- Cuenta en [Supabase](https://supabase.com) (gratuita hasta 500 MB)
- Repositorio en GitHub: `github.com/Pablo25rf/Quality-Scorecard`
- Python 3.10+ local para pruebas

---

## 1. Estructura de ficheros

```
Quality-Scorecard/
├── app.py                                        # Aplicación principal
├── amazon_scorecard_ultra_robust_v3_FINAL.py     # Motor de procesamiento
├── requirements.txt                              # Dependencias Python
├── .gitignore
├── .env.example                                  # Plantilla variables de entorno
├── .streamlit/
│   └── secrets.toml.example                      # Plantilla secrets.toml
├── test_scorecard_v39.py                         # Suite de tests
├── Dockerfile
├── instalar_windows.bat
└── instalar_linux_mac.sh
```

---

## 2. Configurar Supabase

### 2.1 Crear el proyecto
1. Ir a [app.supabase.com](https://app.supabase.com) → **New project**
2. Región: `eu-west-1` (Europa — España)
3. Guarda la contraseña de BD generada

### 2.2 Obtener credenciales
1. **Settings → Database → Connection string**
2. Selecciona **Transaction Pooler** (puerto 6543) — importante para Streamlit Cloud
3. Copia: `host`, `database`, `user`, `password`

### 2.3 Tablas — inicialización automática
No necesitas crear tablas manualmente. Al primer arranque, la app crea y migra todo:

| Tabla | Descripción |
|-------|-------------|
| `scorecards` | Datos por conductor y semana |
| `users` | Usuarios del sistema |
| `center_targets` | Objetivos de calidad por centro |
| `login_attempts` | Rate limiting persistente |
| `station_scorecards` | KPIs del PDF oficial DSP |
| `wh_exceptions` | Excepciones de horas WHC |

Las migraciones son **idempotentes** — puedes arrancar sobre una BD existente sin pérdida de datos.

---

## 3. Variables de entorno

Configura las siguientes variables en Streamlit Cloud Secrets o en el archivo `.env` local.

**Obligatorias:**
```bash
WINIW_ADMIN_USER=<tu_usuario_admin>
WINIW_ADMIN_PASS=<contraseña_segura>
```

**Base de datos (alternativa a secrets.toml):**
```bash
POSTGRES_HOST=<host_supabase>
POSTGRES_PORT=6543
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<tu_password>
```

---

## 4. Deploy en Streamlit Cloud

### 4.1 Subir el código a GitHub
```bash
git clone https://github.com/Pablo25rf/Quality-Scorecard.git
cd Quality-Scorecard
# ... hacer cambios ...
git add .
git commit -m "descripción"
git push origin main
```

### 4.2 Conectar en Streamlit Cloud
1. [share.streamlit.io](https://share.streamlit.io) → **New app**
2. Repositorio: `Pablo25rf/Quality-Scorecard`
3. Branch: `main`
4. Main file path: `app.py`
5. Clic en **Advanced settings** antes de Deploy

### 4.3 Configurar los Secrets
En **Advanced settings → Secrets**, usa el formato del archivo `secrets.toml.example` con tus credenciales reales. El bloque `[postgres]` configura la base de datos; el bloque `[app]` configura las credenciales de acceso a la app.

6. Clic en **Deploy**

---

## 5. Primer acceso

1. Abre la URL de tu app (`tu-app.streamlit.app`)
2. Login con las credenciales configuradas en los Secrets
3. **La app fuerza cambio de contraseña en el primer acceso**
4. Crea usuarios JT desde Admin → Gestión de Usuarios

---

## 6. Entorno local (desarrollo)

```bash
git clone https://github.com/Pablo25rf/Quality-Scorecard.git
cd Quality-Scorecard
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edita .env con tus credenciales
streamlit run app.py
```

Sin `secrets.toml` ni variables Postgres, la app arranca con **SQLite local** automáticamente. El archivo `amazon_quality.db` se crea en el directorio raíz.

---

## 7. Tests antes de hacer push

```bash
WINIW_ADMIN_USER=test WINIW_ADMIN_PASS=test python -m unittest test_scorecard_v39 -v
```

Resultado esperado: **175 tests OK, 13 skipped** (los skipped requieren el PDF real de DMA3 — no son bloqueantes para CI).

---

## 8. Actualizar la app

```bash
# Verificar tests
python -m unittest test_scorecard_v39 -v

# Commit y push
git add app.py amazon_scorecard_ultra_robust_v3_FINAL.py
git commit -m "descripción del cambio"
git push origin main

# Streamlit Cloud detecta el push y redespliega automáticamente (~1-2 min)
```

---

## 9. Solución de problemas frecuentes

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| `psycopg2 not found` | Falta en requirements.txt | Añadir `psycopg2-binary` |
| `Secrets not found` | Mal configurado en Streamlit Cloud | Verificar sección `[postgres]` en Secrets |
| Login bloqueado | Rate limiting activo en BD | Admin → Gestión de Usuarios → desbloquear |
| BD vacía tras redeploy | SQLite local no persiste entre deploys | Usar Supabase en producción |
| Timeout Supabase | Demasiadas conexiones | Usar puerto 6543 (PgBouncer) en vez de 5432 |
| Caché no actualiza | TTL activo | Sidebar → 🔄 Refrescar Datos |
| App muestra versión antigua | Push en rama incorrecta | Verificar que el push fue a `main` |

---

## 10. Seguridad en producción

- Cambiar contraseña del superadmin en el primer acceso
- Rotar credenciales de Supabase periódicamente: Settings → Database
- Revisar logs: Admin → Zona Superadmin → descargar log del sistema
- Los JTs solo pueden ver sus semanas más recientes y su centro asignado

---

## 11. Docker

```bash
# Build
docker build -t winiw-scorecard .

# Run con variables de entorno
docker run -p 8501:8501 --env-file .env winiw-scorecard
```

---

*Quality Scorecard · [@pablo25rf](https://github.com/pablo25rf) · Marzo 2026*
