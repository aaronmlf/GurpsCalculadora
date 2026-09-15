#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
python3 -m venv packaging/.build-venv
packaging/.build-venv/bin/python -m pip install --upgrade pip pyinstaller
packaging/.build-venv/bin/python -m PyInstaller --noconfirm --clean packaging/GurpsCalculadora.spec

echo "Executavel criado em dist/GurpsCalculadora"
