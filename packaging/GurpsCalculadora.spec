# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


project_root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(path), str(path.parent.relative_to(project_root)))
        for folder in ("i18n", "data")
        for path in sorted((project_root / folder).rglob("*.json"))
        if path.is_file() and not path.is_symlink()
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "graphviz",
    ],
    noarchive=False,
    optimize=0,
)

# Filter out graphviz tcl data that causes extraction errors
a.datas = [item for item in a.datas if "graphviz" not in str(item[0]).lower()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GurpsCalculadora",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
