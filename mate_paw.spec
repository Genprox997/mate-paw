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
    # 1) 重型科学/UI 库（历史）
    # 2) PIL 仅用 PNG/GIF/BMP：排除其余 40+ 图片格式插件（每个可能拉二进制解码器）
    # 3) pywin32 仅用 win32gui/win32api/win32con：排除其余子包
    # 4) 未使用的标准库（PyInstaller 默认尽量收集）
    excludes=[
        'numpy', 'scipy', 'pandas', 'PyQt5', 'PySide2', 'cv2', 'torch', 'tensorflow',
        # PIL 格式插件（保留 Png/Gif/Bmp）
        'PIL.JpegImagePlugin', 'PIL.Jpeg2KImagePlugin', 'PIL.TiffImagePlugin',
        'PIL.WebPImagePlugin', 'PIL.PcdImagePlugin', 'PIL.PcxImagePlugin',
        'PIL.PpmImagePlugin', 'PIL.SgiImagePlugin', 'PIL.IcoImagePlugin',
        'PIL.IptcImagePlugin', 'PIL.McIdasImagePlugin', 'PIL.MpegImagePlugin',
        'PIL.MpoImagePlugin', 'PIL.MspImagePlugin', 'PIL.PalmImagePlugin',
        'PIL.GbrImagePlugin', 'PIL.ImtImagePlugin', 'PIL.SpiderImagePlugin',
        'PIL.BufrImagePlugin', 'PIL.CurImagePlugin', 'PIL.DcxImagePlugin',
        'PIL.DdsImagePlugin', 'PIL.EpsImagePlugin', 'PIL.FitsImagePlugin',
        'PIL.FliImagePlugin', 'PIL.FpxImagePlugin', 'PIL.GribStubImagePlugin',
        'PIL.Hdf5StubImagePlugin', 'PIL.IcnsImagePlugin', 'PIL.ImImagePlugin',
        'PIL.MicImagePlugin', 'PIL.PixarImagePlugin', 'PIL.PsdImagePlugin',
        'PIL.WmfImagePlugin', 'PIL.XVThumbImagePlugin', 'PIL.FtexImagePlugin',
        'PIL.ImageQt', 'PIL.ImageWin', 'PIL.ImageGrab', 'PIL.PdfImagePlugin',
        # pywin32 子包（保留 win32gui/win32api/win32con/win32clipboard）
        'win32com', 'win32net', 'win32wnet', 'win32inet', 'win32pdh',
        'win32security', 'servicemanager', 'adodbapi', 'isapi',
        'pythoncom', 'pywin', 'win32trace', 'win32console', 'win32evtlog',
        'win32cred', 'win32ts',
        # 未使用的标准库
        'unittest', 'doctest', 'pydoc', 'lib2to3', 'ensurepip',
        'curses', 'idlelib', 'turtle', 'tkinter.tix',
    ],
    noarchive=False,
    optimize=1,
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
