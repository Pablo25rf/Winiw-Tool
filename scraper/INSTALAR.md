# DSP Scraper — Instalación y uso

## 1. Instalar dependencias (una sola vez)

Abre PowerShell en esta carpeta y ejecuta:

```powershell
pip install -r requirements_scraper.txt
playwright install chromium
```

## 2. Configurar credenciales (una sola vez)

Copia `.env.example` como `.env` en esta misma carpeta:

```powershell
copy .env.example .env
notepad .env
```

Rellena todas las variables:

```
# Amazon DSP Central
DSP_EMAIL=flexborden@winiw.es
DSP_PASS=tu_contraseña_amazon

# Supabase (mismos valores que en Streamlit secrets)
PG_HOST=aws-0-eu-west-1.pooler.supabase.com
PG_PORT=6543
PG_DB=postgres
PG_USER=postgres.TUPROJECTREF
PG_PASS=tu_password_supabase
```

Los valores de Supabase los encuentras en Streamlit Cloud → Settings → Secrets.

## 3. Ejecutar

```powershell
python downloader.py
```

Se abrirá Chrome automáticamente. Si hay MFA, actúas tú en el navegador y el script continúa solo.

Los archivos se guardan en:
```
C:\Users\pablo\Desktop\DSP_Informes\
  └── 2026-W13\
        ├── DIC1\
        │     ├── ES-DIC1-Week13-DSP-Scorecard.pdf
        │     ├── concessions_DIC1_W13.csv
        │     └── quality_DIC1_W13.xlsx
        ├── OGA5\
        ...
```

## 4. Automatizar (opcional) — Task Scheduler

Para que se ejecute solo cada lunes a las 9:00:

1. Abre **Programador de tareas** (busca "Task Scheduler" en inicio)
2. Crear tarea básica → nombre: "DSP Scraper"
3. Desencadenador: Semanalmente → Lunes → 09:00
4. Acción: Iniciar programa
   - Programa: `python`
   - Argumentos: `C:\Users\pablo\Desktop\Winiw-Tool-master\scraper\downloader.py`
   - Iniciar en: `C:\Users\pablo\Desktop\Winiw-Tool-master\scraper`

## Notas

- `headless=False` → el navegador es visible (recomendado al principio)
- Si falla un botón de descarga, avísame con un screenshot de esa página
- La semana se calcula automáticamente: siempre descarga semana_actual - 1
