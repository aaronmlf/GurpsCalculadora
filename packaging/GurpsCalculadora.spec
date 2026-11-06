# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys


project_root = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(project_root))
from tools.release_inputs import resource_paths

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / name), str(Path(name).parent))
        for name in resource_paths(project_root)
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

if sys.platform.startswith("linux"):
    # libmvec is part of glibc and uses the matching loader's private ABI.
    # Like libc and libm, it must be resolved from the target system.
    a.binaries = [item for item in a.binaries if not Path(item[0]).name.startswith("libmvec.so")]

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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
