@echo off
REM ============================================================================
REM QUALITY SCORECARD - INSTALACION RAPIDA (Windows)
REM ============================================================================
REM Version: 3.9
REM Fecha: Marzo 2026
REM ============================================================================

echo.
echo ============================================================================
echo     QUALITY SCORECARD - INSTALACION Y ACTUALIZACION
echo ============================================================================
echo.

REM Verificar Python
echo [1/6] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en PATH
    echo.
    echo Por favor instala Python 3.9 o superior desde:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python instalado correctamente
echo.

REM Crear backup de archivos existentes
echo [2/6] Creando backups de archivos existentes...
if exist app.py (
    echo Backup: app.py -^> app_OLD_%date:~-4,4%%date:~-10,2%%date:~-7,2%.py
    copy app.py app_OLD_%date:~-4,4%%date:~-10,2%%date:~-7,2%.py >nul
)
if exist scorecard_engine.py (
    echo Backup: scorecard_engine.py -^> scorecard_engine_OLD_%date:~-4,4%%date:~-10,2%%date:~-7,2%.py
    copy scorecard_engine.py scorecard_engine_OLD_%date:~-4,4%%date:~-10,2%%date:~-7,2%.py >nul
)
echo [OK] Backups creados
echo.

REM Instalar/Actualizar dependencias
echo [3/6] Instalando dependencias desde requirements.txt...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias
    echo Por favor revisa que requirements.txt existe
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas correctamente
echo.

REM Verificar bcrypt (critico para seguridad)
echo [4/6] Verificando instalacion de bcrypt...
python -c "import bcrypt" >nul 2>&1
if errorlevel 1 (
    echo [ADVERTENCIA] bcrypt no esta instalado correctamente
    echo Intentando instalacion directa...
    python -m pip install bcrypt
    python -c "import bcrypt" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar bcrypt
        echo El sistema funcionara con SHA-256 (menos seguro)
        echo.
        pause
    ) else (
        echo [OK] bcrypt instalado correctamente
    )
) else (
    echo [OK] bcrypt ya esta instalado
)
echo.

REM Copiar archivos mejorados
echo [5/6] Actualizando archivos del sistema...
if exist app.py (
    copy /Y app.py app.py >nul
    echo [OK] app.py actualizada
) else (
    echo [ADVERTENCIA] No se encontro app.py
    echo Usando archivo existente
)

if exist scorecard_engine.py (
    copy /Y scorecard_engine.py scorecard_engine.py >nul
    echo [OK] Motor actualizado
) else (
    echo [ADVERTENCIA] No se encontro scorecard_engine.py
    echo Usando archivo existente
)
echo.

REM Crear directorio de logs
echo [6/6] Creando estructura de directorios...
if not exist logs mkdir logs
echo [OK] Directorio logs/ creado
echo.

REM Verificacion final
echo ============================================================================
echo VERIFICACION FINAL
echo ============================================================================
echo.

python -c "import streamlit; print('[OK] Streamlit version:', streamlit.__version__)"
python -c "import pandas; print('[OK] Pandas version:', pandas.__version__)"
python -c "import bcrypt; print('[OK] Bcrypt instalado')" 2>nul || echo [ADVERTENCIA] Bcrypt no disponible
python -c "import openpyxl; print('[OK] OpenPyXL instalado')"

echo.
echo ============================================================================
echo INSTALACION COMPLETADA EXITOSAMENTE
echo ============================================================================
echo.
echo Proximos pasos:
echo   1. Revisar README.md para documentacion completa
echo   2. Ejecutar: streamlit run app.py
echo   3. Abrir navegador en http://localhost:8501
echo   4. Login con las credenciales configuradas en .env (ver DEPLOY.md)
echo   5. Cambiar contrasena en primer login (obligatorio)
echo.
echo Documentacion disponible:
echo   - README.md: Guia completa del sistema
echo   - DEPLOY.md: Guia de despliegue en Streamlit Cloud / Docker
echo   - CHANGELOG.md: Historial de cambios por version
echo.
echo Logs del sistema:
echo   - logs/scorecard.log (rotativo, max 10MB)
echo.

REM Preguntar si desea ejecutar la aplicacion
set /p EJECUTAR="Deseas ejecutar la aplicacion ahora? (S/N): "
if /i "%EJECUTAR%"=="S" (
    echo.
    echo Iniciando Quality Scorecard...
    echo Presiona Ctrl+C para detener
    echo.
    streamlit run app.py
) else (
    echo.
    echo Para iniciar manualmente ejecuta: streamlit run app.py
    echo.
)

pause
