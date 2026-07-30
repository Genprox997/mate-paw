"""让 tests/ 下的用例能直接 import src/ 里的模块（desktop_pet / config / res_validator / platform_win）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
