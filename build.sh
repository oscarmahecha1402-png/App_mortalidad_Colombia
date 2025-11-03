#!/usr/bin/env bash
set -euo pipefail

# 1) Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Dependencias instaladas correctamente. Listo para iniciar la app."

