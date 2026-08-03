# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import glob


def _collect_tcl_runtime():
    """从当前解释器定位 Tcl/Tk 运行库，返回 PyInstaller 的 (binaries, datas)。

    同时兼容标准 CPython 布局（<prefix>/DLLs、<prefix>/tcl）与
    Anaconda/conda 布局（<prefix>/Library/bin、<prefix>/Library/lib）。
    找不到时返回空列表，不影响其它平台的构建。
    """
    bins, datas = [], []
    roots = []
    for attr in ("base_prefix", "prefix"):
        r = getattr(sys, attr, None)
        if r and r not in roots:
            roots.append(r)

    def add_bin(src, dst="."):
        if src and os.path.isfile(src) and (src, dst) not in bins:
            bins.append((src, dst))

    def add_data(src, dst):
        if src and os.path.isdir(src) and (src, dst) not in datas:
            datas.append((src, dst))

    for root in roots:
        # Anaconda / conda 布局
        lib_bin = os.path.join(root, "Library", "bin")
        lib_lib = os.path.join(root, "Library", "lib")
        for dll in ("tcl86t.dll", "tk86t.dll", "_tkinter.pyd"):
            add_bin(os.path.join(lib_bin, dll))
        # anaconda 的 C 扩展（_ctypes/_tkinter/ssl/sqlite...）依赖 Library/bin 下的
        # 专有 DLL（libffi/zlib/openssl/...），标准 CPython 不需要；冻结时必须一并
        # 收集，否则运行时会 DLL load failed。排除 python 本体 DLL，避免与 PyInstaller
        # 自带的 python 运行时冲突；非 conda 环境此目录不存在，自然不收集。
        # 同时排除体积巨大的重型库（MKL/Qt/WebEngine/OpenBLAS/ICU...），它们与桌面宠物
        # 无关却会让单文件 exe 膨胀到数百 MB。
        _HEAVY = (
            "mkl", "libiomp", "openblas", "blas", "tbb", "dnnl", "mkldnn", "onednn",
            "qt", "webengine", "libclang", "icu", "torch", "caffe", "opencv",
            "ffmpeg", "avcodec", "avformat", "swscale", "swresample", "gdal",
            "geos", "hdf5", "netcdf", "szip", "libgfortran", "libquadmath",
            "sleef", "svml", "scipy", "sklearn", "vtk", "pcl", "ompi", "mpi",
            "libcrypto", "libssl",
        )
        for p in glob.glob(os.path.join(lib_bin, "*.dll")):
            bn = os.path.basename(p).lower()
            if bn.startswith("python") or bn.endswith(".pyd"):
                continue
            if any(h in bn for h in _HEAVY):
                continue
            add_bin(p)
        add_data(os.path.join(lib_lib, "tcl8.6"), "tcl8.6")
        add_data(os.path.join(lib_lib, "tk8.6"), "tk8.6")
        # 标准 CPython 布局
        for dll in ("tcl86t.dll", "tk86t.dll", "_tkinter.pyd"):
            add_bin(os.path.join(root, "DLLs", dll))
        add_data(os.path.join(root, "tcl", "tcl8.6"), os.path.join("tcl", "tcl8.6"))
        add_data(os.path.join(root, "tcl", "tk8.6"), os.path.join("tcl", "tk8.6"))
    return bins, datas


_tcl_bins, _tcl_datas = _collect_tcl_runtime()

a = Analysis(
    ['src\\desktop_pet.py'],
    pathex=[],
    binaries=_tcl_bins,
    # 内嵌默认资源：用户无需把 res/ 放在 exe 旁也能运行（缺失外部 res 时回退到此处）
    # config.default.json 作为配置回退（与 src/config.py 的 DEFAULTS 保持一致）
    datas=[('res', 'res'), ('config.default.json', '.')] + _tcl_datas,
    # 仅保留真实可导入的子模块；类级别的 hiddenimport（如 pystray._win32.Icon）
    # 不是模块，写了只会产生 "not found" 噪声且无效。
    hiddenimports=['pystray._win32', 'pystray._base'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_tk_runtime_hook.py'],
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
