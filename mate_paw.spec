# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\desktop_pet.py'],
    pathex=[],
    binaries=[],
    # 内嵌默认资源：用户无需把 res/ 放在 exe 旁也能运行（缺失外部 res 时回退到此处）
    # config.default.json 作为配置回退（与 src/config.py 的 DEFAULTS 保持一致）
    datas=[('res', 'res'), ('config.default.json', '.')],
    # 仅保留真实可导入的子模块；类级别的 hiddenimport（如 pystray._win32.Icon）
    # 不是模块，写了只会产生 "not found" 噪声且无效。
    hiddenimports=['pystray._win32', 'pystray._base'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除不会被用到的重型依赖，缩小体积
    excludes=['numpy', 'scipy', 'pandas', 'PyQt5', 'PySide2', 'cv2', 'torch', 'tensorflow'],
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
