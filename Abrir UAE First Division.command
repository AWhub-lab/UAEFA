#!/bin/zsh
# Lanzador local de la app Streamlit. Haz doble clic sobre este archivo.

set -e
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! "$PYTHON_BIN" -c "import streamlit" >/dev/null 2>&1; then
    echo "No se ha encontrado Streamlit para $PYTHON_BIN."
    echo "Instala las dependencias con: $PYTHON_BIN -m pip install -r requirements.txt"
    echo ""
    read "?Pulsa Intro para cerrar..."
    exit 1
fi

echo "Abriendo UAE First Division Hub en tu navegador..."
"$PYTHON_BIN" -m streamlit run app.py --server.headless false
