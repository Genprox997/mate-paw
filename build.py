#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
构建 mate_paw 单文件 exe 的便捷脚本。

用法：
    python build.py            # 等价于 pyinstaller --noconfirm mate_paw.spec
    python build.py --clean    # 先清理 build/ dist/ 再构建

产物：dist/mate_paw.exe（已将默认 res/ 与 config.default.json 内嵌，
      缺失外部 res 时自动回退，无需把 res 放在 exe 旁）。
"""
import subprocess
import sys
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = sys.argv[1:]
    spec = os.path.join(HERE, "mate_paw.spec")
    if "--clean" in args:
        for d in ("build", "dist"):
            p = os.path.join(HERE, d)
            if os.path.isdir(p):
                shutil.rmtree(p)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", spec]
    print("运行:", " ".join(cmd))
    subprocess.check_call(cmd)
    print("完成 ->", os.path.join(HERE, "dist", "mate_paw.exe"))


if __name__ == "__main__":
    main()
