# 🚛 Winiw Quality Scorecard v3.9

Sistema de gestión de calidad para Amazon DSP — procesa CSVs y PDFs semanales, calcula scores por conductor y genera scorecards automáticos con visualización en tiempo real.

> **Autor:** [@pablo25rf](https://github.com/pablo25rf)

---

## ✨ Funcionalidades

- **Procesamiento automático** de 7 fuentes CSV/Excel + PDF DSP Scorecard
- **Score ponderado** por conductor con 8 métricas (DNR, DCR, POD, CC, RTS, CDF, FDPS, FS)
- **Calificaciones**: 💎 FANTASTIC · 🥇 GREAT · ⚠️ FAIR · 🛑 POOR
- **Dashboard ejecutivo** con ranking de centros y tendencia semanal
- **Histórico completo** con filtros avanzados y exportación Power BI
- **Gestión de usuarios** con roles (Superadmin / Admin / JT) y rate limiting persistente
- **Targets por centro** configurables desde la interfaz
- **Base de datos dual**: PostgreSQL/Supabase (producción) o SQLite (desarrollo local)
- **WHC count** por estación vía LEFT JOIN automático
- **Columna `anio`** en scorecards y excepciones WHC para filtros rápidos

## 🚀 Instalación rápida

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
# Edita .env con tus credenciales
streamlit run app.py
```

## ⚙️ Configuración

### Variables de entorno (`.env`)
```env
WINIW_ADMIN_USER=admin
WINIW_ADMIN_PASS=password_segura
```

### Base de datos PostgreSQL/Supabase (opcional)
Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y rellena las credenciales.
Sin configuración PostgreSQL, la app usa **SQLite local** automáticamente.

## 🐳 Docker

```bash
docker build -t winiw-scorecard .
docker run -p 8501:8501 --env-file .env winiw-scorecard
```

## 👤 Roles de usuario

| Rol | Permisos |
|-----|----------|
| **Superadmin** | Todo — incluye gestión de usuarios y reset de BD |
| **Admin** | Subir datos, ver scorecards de todos los centros |
| **JT** | Solo ver el scorecard de su centro asignado |

## 📁 Estructura del proyecto

```
WINIW_TOOL/
├── app.py                                    # Interfaz Streamlit
├── amazon_scorecard_ultra_robust_v3_FINAL.py # Motor de procesamiento
├── requirements.txt
├── .env.example
├── .streamlit/
│   └── secrets.toml.example
├── Dockerfile
├── .dockerignore
├── .gitignore
├── instalar_windows.bat
├── instalar_linux_mac.sh
├── test_scorecard_v39.py                     # Suite de tests (159 tests)
└── docs/
    ├── DEPLOY.md
    ├── GUIA_SUPERADMIN.md
    ├── MANUAL_OPERACION_DETALLADO.md
    ├── DOCUMENTACION_TECNICA_IT.md
    └── POWER_BI_GUIA_DEFINITIVA.md
```

## 🧪 Tests

```bash
WINIW_ADMIN_USER=test WINIW_ADMIN_PASS=test python -m unittest test_scorecard_v39 -v
```

159 tests — 0 fallos. 14 skipped requieren el PDF real de DMA3.

## 📋 Changelog

Ver [CHANGELOG.md](CHANGELOG.md)

## 📄 Licencia

© 2026 [@pablo25rf](https://github.com/pablo25rf) · Amazon DSP · Todos los derechos reservados.
