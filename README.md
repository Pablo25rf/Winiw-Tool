# Quality Scorecard

Herramienta de gestión de calidad para operaciones de Logística. Procesa los datos semanales de los centros, calcula el score de cada conductor y genera scorecards automáticos con visualización en tiempo real.

> **Autor:** [@pablo25rf](https://github.com/pablo25rf)

---

## ¿Qué hace?

- Procesa automáticamente los archivos semanales de Logística (CSVs de concesiones, calidad, excepciones WHC y el PDF de scorecard oficial)
- Calcula un **score ponderado por conductor** con 8 métricas: DNR, DCR, POD, CC, RTS, CDF, FDPS y Fantásticos
- Clasifica a cada conductor en cinco niveles: 🌟 FANTASTIC+ · 💎 FANTASTIC · 🥇 GREAT · ⚠️ FAIR · 🛑 POOR
- Muestra un **dashboard ejecutivo** con ranking de centros, tendencia semanal y distribución de niveles
- Mantiene un **histórico completo** filtrable y exportable
- Gestiona **usuarios con roles** (Superadmin / Admin / JT) con control de acceso por centro
- Permite configurar **targets de calidad** por centro desde la propia interfaz
- Funciona con **PostgreSQL/Supabase** en producción o **SQLite local** en desarrollo sin configuración adicional

---

## Instalación rápida

### Windows
```bat
instalar_windows.bat
```

### Linux / Mac
```bash
chmod +x instalar_linux_mac.sh
./instalar_linux_mac.sh
```

### Manual
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edita .env con las credenciales de acceso
streamlit run app.py
```

---

## Configuración

La app requiere dos variables de entorno para arrancar (credenciales del superadmin inicial). Se configuran en el archivo `.env` — ver `.env.example` como plantilla.

Para conectar con PostgreSQL/Supabase en producción, copia `secrets.toml.example` a `.streamlit/secrets.toml` y rellena las credenciales de la base de datos. Sin este archivo la app usa SQLite local automáticamente.

---

## Deploy en Streamlit Cloud

1. Sube el código a GitHub (rama `main`)
2. Conecta el repositorio en [share.streamlit.io](https://share.streamlit.io)
3. Configura los Secrets con las credenciales de Supabase y de acceso
4. Deploy — la app se actualiza automáticamente con cada push a `main`

Ver [DEPLOY.md](DEPLOY.md) para instrucciones detalladas paso a paso.

---

## Docker

```bash
docker build -t quality-scorecard .
docker run -p 8501:8501 --env-file .env quality-scorecard
```

---

## Roles de usuario

| Rol | Acceso |
|-----|--------|
| **Superadmin** | Gestión completa — usuarios, datos, configuración, base de datos |
| **Admin** | Subir datos semanales, ver scorecards de todos los centros |
| **JT** | Ver el scorecard de su centro asignado (semanas recientes) |

---

## Estructura del proyecto

```
Quality-Scorecard/
├── app.py                                    # Interfaz Streamlit
├── scorecard_engine.py # Motor de procesamiento
├── requirements.txt
├── .env.example
├── secrets.toml.example                      # Copiar a .streamlit/secrets.toml
├── .streamlit/
├── Dockerfile
├── instalar_windows.bat
├── instalar_linux_mac.sh
├── test_scorecard_v39.py                     # Suite de tests
└── DEPLOY.md                                 # Guía de despliegue
```

---

## Tests

```bash
QS_ADMIN_USER=test QS_ADMIN_PASS=test python -m unittest test_scorecard_v39 -v
```

175 tests — 0 fallos. 13 skipped requieren el PDF real de DMA3.

---

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md)

---

© 2026 [@pablo25rf](https://github.com/pablo25rf) · Todos los derechos reservados.
