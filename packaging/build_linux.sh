#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
venv=packaging/.build-venv/linux
if [ ! -x "$venv/bin/python" ]; then
    python3 -m venv "$venv"
fi
"$venv/bin/python" -m pip install --disable-pip-version-check --no-deps -r packaging/requirements-build.txt
exec "$venv/bin/python" tools/build_archives.py "$@"
