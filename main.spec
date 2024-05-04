# -*- mode: python ; coding: utf-8 -*-


datas = [
    (
        "venv/Lib/site-packages/UnityPy/resources/uncompressed.tpk",
        "UnityPy/resources",
    ),
    (
        "runtime",
        "runtime",
    ),
]


# (
#             r"runtime\classdata.tpk",
#             r"runtime",
#         ),


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TextTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TextTranslator",
)
