#!/bin/bash
# ============================================================================
# QUALITY SCORECARD - INSTALACION RAPIDA (Linux/macOS)
# ============================================================================
# Version: 3.9
# Fecha: Marzo 2026
# ============================================================================

set -e  # Exit on error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo "========================================================================"
    echo "  $1"
    echo "========================================================================"
    echo ""
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[ADVERTENCIA]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_header "QUALITY SCORECARD - INSTALACION Y ACTUALIZACION"

# [1/6] Verificar Python
echo "[1/6] Verificando Python..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 no está instalado"
    echo ""
    echo "Por favor instala Python 3.9 o superior:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "  macOS: brew install python3"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
print_success "Python $PYTHON_VERSION instalado"
echo ""

# [2/6] Crear backups
echo "[2/6] Creando backups de archivos existentes..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ -f "app.py" ]; then
    cp app.py "app_OLD_$TIMESTAMP.py"
    print_info "Backup: app.py -> app_OLD_$TIMESTAMP.py"
fi

if [ -f "amazon_scorecard_ultra_robust_v3_FINAL.py" ]; then
    cp amazon_scorecard_ultra_robust_v3_FINAL.py "amazon_scorecard_OLD_$TIMESTAMP.py"
    print_info "Backup: amazon_scorecard_ultra_robust_v3_FINAL.py -> amazon_scorecard_OLD_$TIMESTAMP.py"
fi

print_success "Backups creados"
echo ""

# [3/6] Instalar dependencias
echo "[3/6] Instalando dependencias desde requirements.txt..."
print_info "Actualizando pip..."
python3 -m pip install --upgrade pip --quiet

print_info "Instalando dependencias..."
python3 -m pip install -r requirements.txt

if [ $? -eq 0 ]; then
    print_success "Dependencias instaladas correctamente"
else
    print_error "Fallo la instalación de dependencias"
    exit 1
fi
echo ""

# [4/6] Verificar bcrypt
echo "[4/6] Verificando instalación de bcrypt..."
if python3 -c "import bcrypt" 2>/dev/null; then
    print_success "bcrypt ya está instalado"
else
    print_warning "bcrypt no está instalado"
    print_info "Intentando instalación directa..."
    python3 -m pip install bcrypt
    
    if python3 -c "import bcrypt" 2>/dev/null; then
        print_success "bcrypt instalado correctamente"
    else
        print_error "No se pudo instalar bcrypt"
        print_warning "El sistema funcionará con SHA-256 (menos seguro)"
        read -p "Presiona Enter para continuar..."
    fi
fi
echo ""

# [5/6] Copiar archivos mejorados
echo "[5/6] Actualizando archivos del sistema..."

if [ -f "app.py" ]; then
    cp -f app.py app.py
    print_success "app.py actualizada"
else
    print_warning "No se encontró app.py"
    print_info "Usando archivo existente"
fi

if [ -f "amazon_scorecard_ultra_robust_v3_FINAL.py" ]; then
    cp -f amazon_scorecard_ultra_robust_v3_FINAL.py amazon_scorecard_ultra_robust_v3_FINAL.py
    print_success "Motor actualizado"
else
    print_warning "No se encontró amazon_scorecard_ultra_robust_v3_FINAL.py"
    print_info "Usando archivo existente"
fi
echo ""

# [6/6] Crear estructura de directorios
echo "[6/6] Creando estructura de directorios..."
mkdir -p logs
print_success "Directorio logs/ creado"
echo ""

# Verificación final
print_header "VERIFICACION FINAL"

python3 -c "import streamlit; print('[OK] Streamlit version:', streamlit.__version__)"
python3 -c "import pandas; print('[OK] Pandas version:', pandas.__version__)"
python3 -c "import bcrypt; print('[OK] Bcrypt instalado')" 2>/dev/null || echo -e "${YELLOW}[ADVERTENCIA] Bcrypt no disponible${NC}"
python3 -c "import openpyxl; print('[OK] OpenPyXL instalado')"

echo ""
print_header "INSTALACION COMPLETADA EXITOSAMENTE"

echo "Próximos pasos:"
echo "  1. Revisar README.md para documentación completa"
echo "  2. Ejecutar: streamlit run app.py"
echo "  3. Abrir navegador en http://localhost:8501"
echo "  4. Login con el usuario superadmin configurado (ver WINIW_ADMIN_USER / WINIW_ADMIN_PASS)"
echo "  5. Cambiar contraseña en primer login (obligatorio)"
echo ""
echo "Documentación disponible:"
echo "  - README.md: Guía completa del sistema"
echo "  - CAMBIOS_APLICADOS.md: Detalles de mejoras implementadas"
echo ""
echo "Logs del sistema:"
echo "  - logs/scorecard.log (rotativo, max 10MB)"
echo ""

# Preguntar si desea ejecutar la aplicación
read -p "¿Deseas ejecutar la aplicación ahora? (s/n): " EJECUTAR

if [[ $EJECUTAR =~ ^[Ss]$ ]]; then
    echo ""
    echo "Iniciando Quality Scorecard..."
    echo "Presiona Ctrl+C para detener"
    echo ""
    streamlit run app.py
else
    echo ""
    echo "Para iniciar manualmente ejecuta: streamlit run app.py"
    echo ""
fi
