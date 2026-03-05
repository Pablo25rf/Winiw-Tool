---
description: Repository Information Overview
alwaysApply: true
---

# Winiw Quality Scorecard v3.9 Information

## Summary
A comprehensive quality management system for Amazon DSP designed to process weekly CSV and PDF data. It automatically calculates weighted performance scores for drivers based on 8 key metrics (DNR, DCR, POD, CC, RTS, CDF, FDPS, FS) and generates real-time scorecards and rankings. The application features a role-based dashboard, PostgreSQL/Supabase production database support with SQLite failback for development, and automated Power BI export capabilities.

## Structure
- `app.py`: Main Streamlit web application interface and user management.
- `amazon_scorecard_ultra_robust_v3_FINAL.py`: Core processing engine for data ingestion and score calculation.
- `documentacion/`: Technical and user documentation including operation manuals and technical specs.
- `instalar_windows.bat` / `instalar_linux_mac.sh`: Automated installation scripts for different OS environments.
- `test_scorecard_v39.py`: Comprehensive test suite with over 150 unit tests.

## Language & Runtime
**Language**: Python  
**Version**: 3.11 (as specified in Dockerfile)  
**Build System**: pip  
**Package Manager**: pip

## Dependencies
**Main Dependencies**:
- `streamlit`: Web application framework.
- `pandas`: Data manipulation and analysis.
- `numpy`: Numerical processing.
- `openpyxl`: Excel file support.
- `pdfplumber`: PDF data extraction.
- `psycopg2-binary`: PostgreSQL database adapter.
- `bcrypt`: Password hashing and security.
- `python-dotenv`: Environment variable management.

## Build & Installation
```bash
# Manual installation
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## Docker

**Dockerfile**: `Dockerfile`
**Image**: `winiw-scorecard` (suggested tag)
**Configuration**: 
- **Base Image**: `python:3.11-slim`
- **Port**: 8501 (Streamlit default)
- **Features**: Includes `gcc` and `libpq-dev` for database dependencies, specific health checks for Streamlit health status, and headless server configuration.

## Testing

**Framework**: Python `unittest`
**Test Location**: Root directory (`test_scorecard_v39.py`)
**Naming Convention**: `test_*.py`
**Configuration**: Requires `WINIW_ADMIN_USER` and `WINIW_ADMIN_PASS` environment variables for authenticated tests.

**Run Command**:
```bash
WINIW_ADMIN_USER=test WINIW_ADMIN_PASS=test python -m unittest test_scorecard_v39 -v
```
