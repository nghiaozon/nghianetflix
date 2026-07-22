# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ["nghia.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/app-logo-circle.png", "assets"),
        ("assets/app.ico", "assets"),
        ("assets/edit.svg", "assets"),
        ("assets/trash.svg", "assets"),
        ("assets/restore.svg", "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NetflixManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Avoid post-processing DLLs in the one-file archive. Besides being
    # unnecessary for this app, packed binaries are more prone to AV scanning
    # interference while PyInstaller extracts its temporary _MEI runtime.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app.ico",
)
