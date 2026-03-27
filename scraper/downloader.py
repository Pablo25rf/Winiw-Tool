#!/usr/bin/env python3
"""
Amazon DSP Central — Descargador automático de informes semanales
Ejecutar cada lunes para descargar informes de la semana anterior (semana_actual - 1)

Archivos descargados por estación:
  - Scorecard PDF    (safety-dsp-weekly-tab)
  - Concessions CSV  (delivery-associate-weekly-tab)
  - Quality Excel    (quality-dsp-weekly-tab)
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

# Permitir importar scorecard_engine desde la carpeta padre
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dsp-scraper")

# ── Configuración ──────────────────────────────────────────────────────────────
EMAIL      = os.getenv("DSP_EMAIL")
PASSWORD   = os.getenv("DSP_PASS")
COMPANY_ID = "594d9fc0-b0dc-4fd3-a4d4-5c72add32c0b"

STATIONS = [
    "DIC1", "OGA5", "DQB9", "DGA1",
    "DMA3", "OML1", "DCT4", "DCT9", "DQA4",
]

BASE_URL     = "https://logistics.amazon.es"
DOWNLOAD_DIR = Path.home() / "Desktop" / "DSP_Informes"


# ── Semana objetivo ────────────────────────────────────────────────────────────
def get_target_week() -> str:
    """Devuelve la semana anterior a hoy en formato 2026-W13.
    Usa el año ISO (puede diferir del año calendario en semana 1)."""
    target = datetime.now() - timedelta(weeks=1)
    iso_year, iso_week, _ = target.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


# ── URLs ───────────────────────────────────────────────────────────────────────
def build_urls(station: str, week: str) -> dict[str, str]:
    base = (
        f"{BASE_URL}/performance"
        f"?companyId={COMPANY_ID}"
        f"&station={station}"
        f"&timeFrame=Weekly"
        f"&to={week}"
    )
    return {
        "scorecard":  base + "&pageId=dsp_supp_reports&navMenuVariant=external&tabId=safety-dsp-weekly-tab",
        "concessions": base + "&pageId=delivery_associate&tabId=delivery-associate-weekly-tab",
        "quality":    base + "&pageId=dsp_quality&navMenuVariant=external&tabId=quality-dsp-weekly-tab",
    }


# ── Login ──────────────────────────────────────────────────────────────────────
def login(page, first_url: str) -> None:
    """
    Navega directamente a la primera URL de informe.
    Amazon redirige al login y al autenticarse vuelve a esa URL.
    """
    log.info("Navegando a Amazon DSP Central...")
    page.goto(first_url, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(2)

    # Si Amazon redirigió al login, rellenar credenciales
    if "/login" in page.url or "/signin" in page.url or "ap/signin" in page.url:
        log.info("Formulario de login detectado, rellenando credenciales...")

        try:
            page.fill("input[type='email']", EMAIL, timeout=10_000)
        except PlaywrightTimeout:
            page.fill("input[name='email']", EMAIL, timeout=10_000)

        page.keyboard.press("Enter")
        time.sleep(1)

        try:
            page.fill("input[type='password']", PASSWORD, timeout=10_000)
        except PlaywrightTimeout:
            page.fill("input[name='password']", PASSWORD, timeout=10_000)

        page.keyboard.press("Enter")

    log.info("Esperando acceso... (tienes 60s si hay verificación manual)")
    page.wait_for_url(
        lambda url: "/login" not in url and "/signin" not in url and "ap/signin" not in url,
        timeout=60_000,
    )
    time.sleep(3)
    log.info("Login correcto ✓")


# ── Estrategias de descarga ────────────────────────────────────────────────────

def _save_download(dl_info, dest_dir: Path) -> str:
    dl = dl_info.value
    dest = dest_dir / dl.suggested_filename
    dl.save_as(dest)
    return dl.suggested_filename


def click_csv_button(page, dest_dir: Path) -> bool:
    """
    CSV / Excel: botón ↓ a la derecha del buscador 'Encuentra un conductor'.
    Usa coordenadas: encuentra el botón en la misma fila visual que el input.
    """
    # Scroll hasta el buscador
    try:
        page.locator("input[placeholder*='conductor']").first.scroll_into_view_if_needed(timeout=5_000)
        time.sleep(0.5)
    except Exception:
        pass

    try:
        coords = page.evaluate("""() => {
            const input = document.querySelector('input[placeholder*="conductor"]');
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const btns = [...document.querySelectorAll('button')].filter(b => {
                const r = b.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return false;
                return Math.abs((r.top + r.height/2) - (inputRect.top + inputRect.height/2)) < 40;
            });
            if (btns.length === 0) return null;
            const rightmost = btns.reduce((a, b) =>
                b.getBoundingClientRect().left > a.getBoundingClientRect().left ? b : a
            );
            const r = rightmost.getBoundingClientRect();
            return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
        }""")
        if coords:
            log.info(f"    CSV btn coords: ({coords['x']:.0f}, {coords['y']:.0f})")
            with page.expect_download(timeout=30_000) as dl_info:
                page.mouse.click(coords["x"], coords["y"])
            fname = _save_download(dl_info, dest_dir)
            log.info(f"    ✓ {fname}")
            return True
    except Exception as e:
        log.warning(f"    ✗ CSV btn falló: {e}")

    return False


def click_pdf_link(page, dest_dir: Path) -> bool:
    """
    PDF Scorecard: en la página de informes complementarios aparece una lista
    de links. El scorecard tiene el patrón: ES-TDSL-XXX-WeekNN-DSP-Scorecard-3.0.pdf
    """
    selectors = [
        "a:has-text('DSP-Scorecard')",
        "a:has-text('DSP Scorecard')",
        "a[href*='DSP-Scorecard']",
        "a[href*='Scorecard']",
        "a:has-text('Scorecard')",
    ]
    for sel in selectors:
        try:
            lnk = page.locator(sel).first
            if lnk.is_visible(timeout=2_000):
                log.info(f"    PDF link: {sel}")
                with page.expect_download(timeout=30_000) as dl_info:
                    lnk.click()
                fname = _save_download(dl_info, dest_dir)
                log.info(f"    ✓ {fname}")
                return True
        except Exception:
            continue
    return False


def download_report(page, url: str, dest_dir: Path, label: str, file_type: str) -> bool:
    """Navega a la URL y descarga según el tipo de archivo."""
    log.info(f"  → {label} ({file_type})")
    try:
        page.goto(url, wait_until="networkidle", timeout=30_000)
        time.sleep(2)  # Esperar renderizado React/SPA

        if file_type == "pdf":
            ok = click_pdf_link(page, dest_dir)
        else:
            ok = click_csv_button(page, dest_dir)

        if not ok:
            log.warning(f"    ✗ No se encontró el botón/enlace de descarga para {label}")
        return ok

    except PlaywrightTimeout:
        log.error(f"  ✗ Timeout navegando a {label}")
        return False
    except Exception as e:
        log.error(f"  ✗ Error en {label}: {e}")
        return False


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    if not EMAIL or not PASSWORD:
        log.error("Faltan credenciales. Crea un archivo .env con DSP_EMAIL y DSP_PASS")
        return

    week = get_target_week()
    week_dir = DOWNLOAD_DIR / week
    week_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"Semana objetivo : {week}")
    log.info(f"Destino         : {week_dir}")
    log.info(f"Estaciones      : {', '.join(STATIONS)}")
    log.info("")

    results: dict[str, dict[str, str]] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,          # False = ves el navegador (útil para MFA)
            slow_mo=300,             # 300ms entre acciones, más humano
        )
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(30_000)

        # Login usando la URL del primer informe de la primera estación
        first_urls = build_urls(STATIONS[0], week)
        login(page, first_urls["scorecard"])

        for station in STATIONS:
            log.info(f"\n{'─'*40}")
            log.info(f"Estación: {station}")
            station_dir = week_dir / station
            station_dir.mkdir(exist_ok=True)

            urls = build_urls(station, week)
            results[station] = {}

            # scorecard → PDF (link de texto), concessions y quality → CSV/Excel (botón icono)
            file_types = {"scorecard": "pdf", "concessions": "csv", "quality": "csv"}

            for report_type, url in urls.items():
                ok = download_report(page, url, station_dir, report_type, file_types[report_type])
                results[station][report_type] = "✓" if ok else "✗"

        browser.close()

    # ── Resumen final ──────────────────────────────────────────────────────────
    log.info(f"\n{'═'*50}")
    log.info(f"RESUMEN — {week}")
    log.info(f"{'═'*50}")
    total_ok = total_fail = 0
    for station, files in results.items():
        parts = "  |  ".join(f"{k}: {v}" for k, v in files.items())
        log.info(f"  {station:<6}  {parts}")
        total_ok   += sum(1 for v in files.values() if v == "✓")
        total_fail += sum(1 for v in files.values() if v == "✗")

    log.info(f"\n  Éxito: {total_ok}  |  Fallos: {total_fail}")
    log.info(f"  Archivos en: {week_dir}")

    # ── Subir a Supabase con lo que se haya descargado ─────────────────────────
    if total_fail > 0:
        log.warning(f"  {total_fail} fallos de descarga — subiendo igualmente lo disponible.")
    process_downloads(week_dir, week)


# ── Supabase / Engine ──────────────────────────────────────────────────────────

def get_db_config() -> dict:
    """Lee credenciales Supabase del .env y devuelve db_config para scorecard_engine."""
    host = os.getenv("PG_HOST")
    if not host:
        log.warning("PG_HOST no definido en .env — saltando subida a Supabase")
        return {}
    return {
        "type": "postgresql",
        "host": host,
        "port": int(os.getenv("PG_PORT", 6543)),
        "database": os.getenv("PG_DB", "postgres"),
        "user": os.getenv("PG_USER"),
        "password": os.getenv("PG_PASS"),
    }


def process_station(engine, station_dir: Path, week: str, year: int, db_config: dict) -> dict:
    """
    Procesa los archivos descargados de una estación y los sube a Supabase.
    Devuelve dict con resultado por tipo: {'pdf': '✓', 'csv': '✓'}
    """
    center = station_dir.name   # DIC1, OGA5, etc.
    week_code = f"W{int(week.split('-W')[1]):02d}"  # 2026-W12 → W12
    result = {"pdf": "–", "csv": "–"}

    # ── PDF Scorecard ──────────────────────────────────────────────────────────
    # Ordenar por fecha de modificación: el más reciente primero
    pdfs = sorted(station_dir.glob("*DSP-Scorecard*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)
    if pdfs:
        pdf_path = pdfs[0]
        log.info(f"    PDF: {pdf_path.name}")
        try:
            pdf_bytes = pdf_path.read_bytes()
            parsed = engine.parse_dsp_scorecard_pdf(pdf_bytes)
            if parsed.get("ok"):
                ok_st, err_st = engine.save_station_scorecard(
                    parsed["station"], week_code, center,
                    db_config=db_config, uploaded_by="AutoScraper", year=year,
                )
                if not ok_st:
                    log.error(f"    save_station_scorecard falló: {err_st}")

                n_upd, n_miss = engine.update_drivers_from_pdf(
                    parsed["drivers"], week_code, center,
                    db_config=db_config, year=year,
                )
                if n_miss > 0:
                    log.warning(f"    {n_miss} conductores del PDF no encontrados en DB")

                ok_wh = engine.save_wh_exceptions(
                    parsed["wh"], week_code, center,
                    db_config=db_config, uploaded_by="AutoScraper", year=year,
                )
                if not ok_wh:
                    log.error("    save_wh_exceptions falló")

                log.info(f"    PDF subido ✓ ({len(parsed['drivers'])} conductores)")
                result["pdf"] = "✓"
            else:
                log.warning(f"    PDF parse falló: {parsed.get('errors')}")
                result["pdf"] = "✗"
        except Exception as e:
            log.error(f"    PDF error: {e}", exc_info=True)
            result["pdf"] = "✗"
    else:
        log.warning(f"    PDF no encontrado en {station_dir}")

    # ── Concessions CSV + Quality CSV ──────────────────────────────────────────
    # Ordenar por fecha de modificación: el más reciente primero
    concessions = sorted(
        list(station_dir.glob("*Concessions*.csv")) + list(station_dir.glob("*Concessions*.xlsx")),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )
    quality = sorted(
        list(station_dir.glob("*Quality*.csv")) + list(station_dir.glob("*Quality*.xlsx")),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )

    if concessions:
        log.info(f"    CSV: {concessions[0].name}" + (f" + {quality[0].name}" if quality else ""))
        try:
            targets = engine.get_center_targets(center, db_config=db_config)
            df = engine.process_single_batch(
                path_concessions=str(concessions[0]),
                path_quality=str(quality[0]) if quality else None,
                targets=targets,
            )
            if df is not None and not df.empty:
                ok, err = engine.save_to_database(
                    df, week_code, center,
                    db_config=db_config, uploaded_by="AutoScraper", year=year,
                )
                if ok:
                    log.info(f"    CSV subido ✓ ({len(df)} conductores)")
                    result["csv"] = "✓"
                else:
                    log.error(f"    CSV save error: {err}")
                    result["csv"] = "✗"
            else:
                log.warning("    CSV proceso devolvió vacío")
                result["csv"] = "✗"
        except Exception as e:
            log.error(f"    CSV error: {e}", exc_info=True)
            result["csv"] = "✗"
    else:
        log.warning(f"    Concessions no encontrado en {station_dir}")

    return result


def process_downloads(week_dir: Path, week: str) -> None:
    """Procesa todos los archivos descargados y los sube a Supabase."""
    db_config = get_db_config()
    if not db_config:
        log.warning("Sin config de Supabase — proceso de subida omitido.")
        return

    try:
        import scorecard_engine as engine
    except ImportError as e:
        log.error(f"No se pudo importar scorecard_engine: {e}")
        return

    year = int(week.split("-")[0])  # 2026-W12 → 2026

    log.info(f"\n{'═'*50}")
    log.info(f"SUBIENDO A SUPABASE — {week}")
    log.info(f"{'═'*50}")

    upload_results = {}
    for station_dir in sorted(week_dir.iterdir()):
        if not station_dir.is_dir():
            continue
        log.info(f"\n  Estación: {station_dir.name}")
        upload_results[station_dir.name] = process_station(engine, station_dir, week, year, db_config)

    # Resumen subida
    log.info(f"\n{'─'*50}")
    log.info("RESUMEN SUBIDA")
    log.info(f"{'─'*50}")
    for station, res in upload_results.items():
        log.info(f"  {station:<6}  PDF: {res['pdf']}  |  CSV: {res['csv']}")


# ── Main actualizado ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
