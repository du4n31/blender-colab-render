#!/usr/bin/env bash
set -euo pipefail

echo "=== Configurando entorno de desarrollo ==="

# Crear venv si no existe
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "venv creado"
fi

source venv/bin/activate

# Instalar dependencias
pip install --upgrade pip
pip install pytest pytest-mock

echo "=== Listo ==="
echo "Activa el entorno con: source venv/bin/activate"
