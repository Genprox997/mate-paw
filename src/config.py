"""
mate-paw 配置系统
================

把原先散落在 desktop_pet.py 顶部的硬编码常量抽到这里，支持从外部
`config.json` 覆盖，并始终带有默认值回退。这样无需改代码即可调节
宠物行为 / 外观 / 日志等级。

加载优先级（后者覆盖前者）：DEFAULTS -> 找到的 config.json。
"""

import copy
import json
import os
import sys

# 单一版本来源：打包与“关于/--version”都引用它
APP_VERSION = "5.1.0"

# 所有可调参数的默认值。键名与 desktop_pet.py 中原来的常量一一对应。
DEFAULTS = {
    # 渲染 / 外观
    "fps": 30,
    "sprite_w": 180,
    "sprite_h": 260,
    "bob_amp": 6,
    "bob_speed": 0.18,
    "scale_range": 0.025,
    # 渲染缓存（A. 性能）：PhotoImage LRU 上限；调小省内存、调大减少重建
    "photo_cache_max": 384,
    # 气泡对话
    "bubble_font_size": 34,
    "bubble_duration_ms": 2500,
    # 爬行行为
    "crawl_speed_min": 1.5,
    "crawl_speed_max": 3.5,
    "pause_chance": 0.006,
    "look_chance": 0.004,
    "pause_duration": [40, 120],
    "look_duration": [50, 150],
    "dir_change_chance": 0.012,
    # 防连发冷却（E：避免同一动作被连续触发导致刷新过快）
    # 动作（如张望）结束后，强制安静爬行 action_gap 帧，再允许下一次动作；
    # 同一动作在 action_repeat_block 帧窗口内禁止再次触发。
    "action_gap": 30,
    "action_repeat_block": 240,
    # 朝向翻转保护（F：避免精灵一秒内多次左右镜像导致观感差）
    # facing_flip_cooldown：两次翻转之间的最低帧间隔（30fps 下 15 帧≈0.5s，即最多 2 次/秒）；
    # facing_vx_threshold：水平速度死区，|vx| 小于该值视为无明显水平方向，保持当前朝向；
    # facing_cursor_threshold：看向光标时，光标与宠物中心横向距离小于该值不翻转（像素）。
    "facing_flip_cooldown": 15,
    "facing_vx_threshold": 0.4,
    "facing_cursor_threshold": 20,
    # 空闲 / 随机行为（C：行为丰富度）
    "idle_chance": 0.0008,
    "idle_duration": [60, 160],
    "sleep_chance": 0.0004,
    "sleep_duration": [600, 1800],
    "wave_chance": 0.0004,
    "wave_duration": [40, 90],
    "blink_chance": 0.0015,
    "blink_duration": [6, 14],
    # 运行时
    "log_level": "INFO",
    # 交互与体验（D）
    "pause_all_on_start": False,
    "follow_cursor": False,
    "idle_bubble_chance": 0.0006,
    "tap_react": True,
    "poke_bubble": "喂！",
    "sound": False,
    "bubble_lines": ["爸！", "你好呀~", "陪我玩", "吱吱", "摸摸我", "好痒", "嘻嘻",
                     "别戳啦", "再戳就咬你", "汪？", "饿饿", "今天也要加油", "在发呆…"],
    # 抠图色键容差（四角采样色键方案，见 desktop_pet.chroma_key）
    "chroma_tolerance": 40,
}


class Config:
    """字典式配置的轻量封装：支持属性访问与保存。"""

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", dict(data))

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getattr__(self, name):
        data = object.__getattribute__(self, "_data")
        if name in data:
            return data[name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name == "_data":
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value

    def to_dict(self) -> dict:
        return dict(self._data)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)


def find_config_path() -> str | None:
    """按优先级查找已存在的 config.json（与 get_res_dir 同源思路）。"""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), "config.json"))
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "config.default.json"))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, "config.json"))
        candidates.append(os.path.join(os.path.dirname(script_dir), "config.json"))
    candidates.append(os.path.join(os.getcwd(), "config.json"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def load_config(path: str | None = None):
    """加载配置：DEFAULTS 打底，再叠加用户 config.json。

    返回 (Config, 实际来源路径或 'defaults')。
    """
    data = copy.deepcopy(DEFAULTS)
    src = path or find_config_path()
    if src and os.path.isfile(src):
        try:
            with open(src, encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                data.update(user)
        except Exception:
            src = "defaults(bad-json)"
    return Config(data), (src or "defaults")


def default_config_path() -> str:
    """返回『应当写入的』config.json 路径：exe 同级或 cwd。"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    return os.path.join(os.getcwd(), "config.json")
