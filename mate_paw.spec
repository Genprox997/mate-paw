# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\desktop_pet.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pystray._win32', 'pystray._base', 'pystray._win32.NotifyIcon', 'pystray._win32.Icon', 'pystray._win32.Menu', 'pystray._win32.MenuItem', 'pystray._win32._NotifyIcon', 'pystray._win32._Icon', 'pystray._win32._Menu', 'pystray._win32._MenuItem'],
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
    name='mate_paw',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
