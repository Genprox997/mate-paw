# -*- coding: utf-8 -*-
"""PyInstaller 运行时钩子：冻结后把 Tcl/Tk 指到打包进 exe 的运行库。

anaconda/conda 布局下的 tcl 不在 PyInstaller 默认搜索路径，构建时不会自动
收集，导致冻结后的 exe `import tkinter` 失败。此钩子在运行时设置
TCL_LIBRARY / TK_LIBRARY，使其指向打包目录里的 tcl8.6 / tk8.6。
"""
import os
import sys

if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    tcl = os.path.join(base, "tcl8.6")
    tk = os.path.join(base, "tk8.6")
    if os.path.isdir(tcl):
        os.environ.setdefault("TCL_LIBRARY", tcl)
    if os.path.isdir(tk):
        os.environ.setdefault("TK_LIBRARY", tk)
