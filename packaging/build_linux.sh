#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
python3 -m pip install --upgrade pyinstaller
python3 -m PyInstaller --noconfirm --clean packaging/GurpsCalculadora.spec

echo "Executavel criado em dist/GurpsCalculadora"
