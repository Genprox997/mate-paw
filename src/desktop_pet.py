"""
桌面宠物应用 - mate-paw (v5.1)
多只"人形猴子"在桌面自由爬行玩耍，感知窗口边缘作为障碍物。
配置来自 config.json（带默认值，见 src/config.py）。
4 个"人形猴子"在桌面自由爬行玩耍，感知窗口边缘作为障碍物。
交互：
  - 鼠标左键拖动人物到其他位置
  - 鼠标右键人物切换姿态（爬行 / 坐姿 / 招手 循环）
  - 鼠标左键双击人物：宠物喊"爸！"并弹出气泡对话
  - 任务栏系统托盘图标（pystray）：每人显隐开关 + 退出
  - ESC 关闭程序
"""

import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import random
import math
import os
import sys
import time
import json
import queue
import threading
import ctypes
import logging
from collections import OrderedDict
from platform_win import (
    HAS_WIN32,
    get_screen_size,
    find_pet_window,
    set_layered_tool_window,
    set_window_region,
    set_window_region_fullscreen,
    enum_window_rects,
    install_mouse_hook,
    uninstall_mouse_hook,
    MSLLHOOKSTRUCT,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEMOVE,
    WM_RBUTTONDOWN,
    WM_RBUTTONUP,
)

import pystray

from config import load_config, APP_VERSION, default_config_path, Config
from res_validator import validate_res

# ============================================================
# 配置（来自 config.json，带默认值回退，见 src/config.py）
# ============================================================
CONFIG, CONFIG_SOURCE = load_config()


def apply_config(cfg):
    """把配置值同步到模块级常量；设置面板改完调用它即可实时生效。"""
    global SPRITE_W, SPRITE_H, FPS, UPDATE_MS, BOB_AMP, BOB_SPEED, SCALE_RANGE, \
        PHOTO_CACHE_MAX, \
        BUBBLE_FONT_SIZE, BUBBLE_DURATION_MS, CRAWL_SPEED_MIN, CRAWL_SPEED_MAX, \
        PAUSE_CHANCE, LOOK_CHANCE, PAUSE_DURATION, LOOK_DURATION, DIR_CHANGE_CHANCE, \
        IDLE_CHANCE, IDLE_DURATION, SLEEP_CHANCE, SLEEP_DURATION, WAVE_CHANCE, \
        WAVE_DURATION, BLINK_CHANCE, BLINK_DURATION, IDLE_BUBBLE_CHANCE, \
        FOLLOW_CURSOR, TAP_REACT, POKE_BUBBLE, ACTION_GAP, ACTION_REPEAT_BLOCK, \
        FACING_FLIP_COOLDOWN, FACING_VX_THRESHOLD, FACING_CURSOR_THRESHOLD
    SPRITE_W = cfg.sprite_w
    SPRITE_H = cfg.sprite_h
    FPS = cfg.fps
    UPDATE_MS = 1000 // FPS
    BOB_AMP = cfg.bob_amp
    BOB_SPEED = cfg.bob_speed
    SCALE_RANGE = cfg.scale_range
    PHOTO_CACHE_MAX = int(cfg.photo_cache_max)
    BUBBLE_FONT_SIZE = cfg.bubble_font_size
    BUBBLE_DURATION_MS = cfg.bubble_duration_ms
    CRAWL_SPEED_MIN = cfg.crawl_speed_min
    CRAWL_SPEED_MAX = cfg.crawl_speed_max
    PAUSE_CHANCE = cfg.pause_chance
    LOOK_CHANCE = cfg.look_chance
    PAUSE_DURATION = tuple(cfg.pause_duration)
    LOOK_DURATION = tuple(cfg.look_duration)
    DIR_CHANGE_CHANCE = cfg.dir_change_chance
    IDLE_CHANCE = cfg.idle_chance
    IDLE_DURATION = tuple(cfg.idle_duration)
    SLEEP_CHANCE = cfg.sleep_chance
    SLEEP_DURATION = tuple(cfg.sleep_duration)
    WAVE_CHANCE = cfg.wave_chance
    WAVE_DURATION = tuple(cfg.wave_duration)
    BLINK_CHANCE = cfg.blink_chance
    BLINK_DURATION = tuple(cfg.blink_duration)
    IDLE_BUBBLE_CHANCE = cfg.idle_bubble_chance
    FOLLOW_CURSOR = bool(cfg.follow_cursor)
    TAP_REACT = bool(cfg.tap_react)
    POKE_BUBBLE = str(cfg.poke_bubble)
    ACTION_GAP = int(cfg.action_gap)
    ACTION_REPEAT_BLOCK = int(cfg.action_repeat_block)
    FACING_FLIP_COOLDOWN = int(cfg.facing_flip_cooldown)
    FACING_VX_THRESHOLD = float(cfg.facing_vx_threshold)
    FACING_CURSOR_THRESHOLD = int(cfg.facing_cursor_threshold)
    setup_logging(cfg.log_level)


def set_config(cfg):
    """替换全局 CONFIG 并应用（设置对话框保存时调用）。"""
    global CONFIG
    CONFIG = cfg
    apply_config(cfg)


# ============================================================
# 行为状态 -> 姿态组 映射 & 纯决策函数（不依赖 Tk，便于单测）
# ============================================================
# 不同行为状态对应的「命名姿态组」。资源里要有同名子目录才生效，
# 缺失时 set_pose_group 自动 no-op，宠物保持当前姿态，行为逻辑不受影响。
STATE_POSE = {
    'crawling': 'walk',
    'pausing': 'idle',
    'looking': 'look',
    'idle': 'idle',
    'sleep': 'sleep',
    'wave': 'wave',
    'blink': 'blink',
}


def choose_crawl_action(r, pause, look, turn, idle, sleep, wave, blink, exclude=None):
    """根据一次 [0,1) 随机值决定爬行中发生的动作。

    返回 'pause' / 'look' / 'turn' / 'idle' / 'sleep' / 'wave' / 'blink' / None。
    概率按入参顺序累加到阈值，第一个命中的即返回；都不命中返回 None（继续爬行）。

    exclude: 若某动作刚触发过、处于冷却窗口，应传入该动作名以跳过它，
        避免同一动作（如左右张望）被连续触发。被排除动作的概率会被其余动作
        按比例吸收，整体触发节奏不变。
    """
    thr = 0.0
    for action, chance in (
        ('pause', pause), ('look', look), ('turn', turn),
        ('idle', idle), ('sleep', sleep), ('wave', wave), ('blink', blink),
    ):
        if action == exclude:
            continue
        thr += chance
        if r < thr:
            return action
    return None


def facing_toward(from_x, target_x):
    """from_x 处的人物应朝左(False)还是朝右(True)以面向 target_x。"""
    return target_x >= from_x


def is_tap(dx, dy, dt_ms, move_thresh=8, max_dt_ms=350):
    """判断一次按下-释放是否为「轻点」（而非拖拽）：位移小且时间短。"""
    return math.hypot(dx, dy) <= move_thresh and dt_ms <= max_dt_ms


def pick_phrase(phrases, rng=random.choice):
    """从语料里随机挑一句；语料为空返回空串。"""
    if not phrases:
        return ""
    return rng(phrases)


# 支持的动作姿态图片格式（常量，不随配置变化）
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff')

# ============================================================
# 日志（替代散落的 print；打包后额外写文件到 %APPDATA%/mate_paw）
# ============================================================
log = logging.getLogger("mate_paw")


def setup_logging(level_name: str = "INFO") -> None:
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)
    if getattr(sys, "frozen", False):
        try:
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            d = os.path.join(appdata, "mate_paw")
            os.makedirs(d, exist_ok=True)
            fh = logging.FileHandler(os.path.join(d, "mate_paw.log"), encoding="utf-8")
            fh.setFormatter(fmt)
            log.addHandler(fh)
        except Exception:
            pass
    log.setLevel(level)


# 导入即应用一次配置（同时完成日志初始化），保证任何位置的 log 调用都有去处
apply_config(CONFIG)


def state_path():
    """状态文件路径：与 config.json 同目录（exe 目录或 cwd），记录每只宠物位置/显隐/姿态。"""
    return os.path.join(os.path.dirname(default_config_path()), "state.json")

# ============================================================
# 工具函数
# ============================================================


def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def get_res_dir():
    """
    返回程序运行文件夹下的 res 目录（人物资源根目录）。
    兼容两种运行方式：
      - 打包后的 exe：res 放在 exe 同级目录（sys.executable 所在目录）
      - 开发模式：依次在 脚本目录 / 脚本上级目录(项目根) / 当前工作目录 中查找已存在的 res
    若都找不到，则回退到当前工作目录下的 res（运行时再提示缺失）。
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        candidates.append(os.path.dirname(sys.executable))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(script_dir)               # 脚本所在目录
        candidates.append(os.path.dirname(script_dir))  # 项目根目录（脚本在子目录时）
    candidates.append(os.getcwd())                  # 当前工作目录

    for base in candidates:
        d = os.path.join(base, 'res')
        if os.path.isdir(d):
            return d
    # 打包后若外部没有 res，回退到内嵌的默认资源（PyInstaller 解包到 _MEIPASS）
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        d = os.path.join(sys._MEIPASS, 'res')
        if os.path.isdir(d):
            return d
    # 未找到现成的 res，回退到 cwd/res 并交由调用方提示
    return os.path.join(os.getcwd(), 'res')


def chroma_key(im, tolerance=None):
    """色键去背景：采样四角+四边中点作为背景色，移除与之接近的像素。

    与旧 remove_light_bg（固定阈值 248 会误删白色衣服）不同：
      - 仅对不透明像素判定，透明 PNG（如 rembg 产出）直接跳过，前景白衣服得以保留；
      - 背景色取自图片边缘采样的中位数，适配任意背景色，而非只认纯白。
    tolerance 为 RGB 欧氏距离阈值，默认取 CONFIG.chroma_tolerance。
    """
    if im.mode != 'RGBA':
        im = im.convert('RGBA')
    if tolerance is None:
        tolerance = CONFIG.chroma_tolerance
    w, h = im.size
    px = im.load()
    # 边缘采样点：四角 + 四边中点
    pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
           (w // 2, 0), (0, h // 2), (w - 1, h // 2), (w // 2, h - 1)]
    rs = [px[x, y][0] for (x, y) in pts if px[x, y][3] > 10]
    gs = [px[x, y][1] for (x, y) in pts if px[x, y][3] > 10]
    bs = [px[x, y][2] for (x, y) in pts if px[x, y][3] > 10]
    if not rs:
        return im  # 边缘全透明：已是透明图，无需处理（白衣服等前景保留）
    br = sorted(rs)[len(rs) // 2]
    bg = sorted(gs)[len(gs) // 2]
    bb = sorted(bs)[len(bs) // 2]
    out = im.copy()
    op = out.load()
    t2 = tolerance * tolerance
    for y in range(h):
        for x in range(w):
            r, g, b, a = op[x, y]
            if a == 0:
                continue
            if (r - br) ** 2 + (g - bg) ** 2 + (b - bb) ** 2 <= t2:
                op[x, y] = (r, g, b, 0)
    return out


def get_window_rects(cache_ttl=2.0):
    now = time.time()
    cache = getattr(get_window_rects, '_cache', None)
    if cache is not None and now - get_window_rects._cache_time < cache_ttl:
        return cache

    screen_w, screen_h = get_screen_size()
    rects = enum_window_rects(screen_w, screen_h, 'mate_paw')
    get_window_rects._cache = rects
    get_window_rects._cache_time = now
    return rects


def rects_overlap(r1, r2):
    return not (r1[2] <= r2[0] or r1[0] >= r2[2] or r1[3] <= r2[1] or r1[1] >= r2[3])


def compute_pet_rects(pets, screen_w, screen_h):
    """收集所有可见宠物在屏幕坐标下的矩形并集（窗口局部点击区域用）。

    纯函数（不依赖 Tk / win32），便于单测「布局未变 -> 签名不变 -> 跳过 SetWindowRgn」。
    """
    rects = []
    for pet in pets:
        if not pet.visible:
            continue
        x1 = max(0, int(pet.x))
        y1 = max(0, int(pet.y))
        x2 = min(screen_w, int(pet.x) + SPRITE_W)
        y2 = min(screen_h, int(pet.y) + SPRITE_H)
        if x2 <= x1 or y2 <= y1:
            continue
        rects.append((x1, y1, x2, y2))
    return rects


def make_tray_icon_image(size=64):
    """生成系统托盘图标：棕色圆脸 + 耳朵（猴子风格）。"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 4
    # 头部圆
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(139, 90, 43, 255))
    # 左耳
    draw.ellipse([cx - r - 8, cy - r + 4, cx - r + 12, cy - r + 28], fill=(139, 90, 43, 255))
    # 右耳
    draw.ellipse([cx + r - 12, cy - r + 4, cx + r + 8, cy - r + 28], fill=(139, 90, 43, 255))
    # 眼睛
    er = size // 10
    draw.ellipse([cx - r // 2 - er, cy - r // 3 - er,
                  cx - r // 2 + er, cy - r // 3 + er], fill=(255, 255, 255, 255))
    draw.ellipse([cx + r // 2 - er, cy - r // 3 - er,
                  cx + r // 2 + er, cy - r // 3 + er], fill=(255, 255, 255, 255))
    # 瞳孔
    pr = er // 2
    draw.ellipse([cx - r // 2 - pr, cy - r // 3 - pr,
                  cx - r // 2 + pr, cy - r // 3 + pr], fill=(40, 30, 20, 255))
    draw.ellipse([cx + r // 2 - pr, cy - r // 3 - pr,
                  cx + r // 2 + pr, cy - r // 3 + pr], fill=(40, 30, 20, 255))
    # 嘴巴
    mw = size // 5
    draw.arc([cx - mw, cy, cx + mw, cy + mw], start=0, end=180, fill=(80, 50, 25, 255), width=2)
    return img


# 注：pystray.Icon 直接接受 PIL.Image 作为托盘图标，无需转成 Windows HICON，
# 故移除原先的 pil_to_hicon（基于 tempfile + win32gui.LoadImage）。



# ============================================================
# 系统托盘图标（基于 pystray，跨平台、稳定）
# ============================================================
class PystrayTrayIcon:
    """使用 pystray 实现的系统托盘图标，菜单含每人显隐开关 + 退出。"""

    def __init__(self, pets, on_quit_callback, on_toggle_callback=None,
                 on_pause_callback=None, on_settings_callback=None,
                 on_about_callback=None, get_paused_callback=None,
                 on_show_all_callback=None, on_hide_all_callback=None,
                 on_poke_callback=None):
        """
        pets: list of MatePaw 对象（需要有 .label 和 .visible 属性）
        on_quit_callback: 退出回调函数（由 pystray 在后台线程调用，应自行调度到主线程）
        on_toggle_callback: 切换人物显隐的回调，参数为人物在 pets 列表中的索引
        on_pause_callback / on_settings_callback / on_about_callback: 对应菜单动作
        on_show_all_callback / on_hide_all_callback / on_poke_callback: 全部显示/隐藏/戳一下
        get_paused_callback: 返回当前是否全局暂停（用于菜单项文案）
        """
        self.pets = pets
        self.on_quit = on_quit_callback
        self.on_toggle = on_toggle_callback
        self.on_pause = on_pause_callback
        self.on_settings = on_settings_callback
        self.on_about = on_about_callback
        self.get_paused = get_paused_callback
        self.on_show_all = on_show_all_callback
        self.on_hide_all = on_hide_all_callback
        self.on_poke = on_poke_callback
        self.icon = None

    def _is_paused(self):
        try:
            return bool(self.get_paused()) if self.get_paused else False
        except Exception:
            return False

    def _on_pause(self, *args):
        if self.on_pause:
            self.on_pause()
        # 切换后刷新菜单文案（恢复/暂停）
        try:
            if self.icon is not None:
                self.icon.update_menu()
        except Exception:
            pass

    def _on_settings(self, *args):
        if self.on_settings:
            self.on_settings()

    def _on_about(self, *args):
        if self.on_about:
            self.on_about()

    def _build_menu(self):
        """构建托盘右键菜单：每人显隐开关 + 暂停/恢复 + 设置 + 关于 + 退出。

        pystray 的 checked 回调在每次展开菜单时求值，因此勾选状态始终反映
        当前 pet.visible，无需手动刷新菜单。
        """
        items = []
        for i, pet in enumerate(self.pets):
            # 捕获 i 到默认参数，避免闭包 late binding 让所有项都指向最后一个索引
            items.append(
                pystray.MenuItem(
                    pet.label,
                    # 注意：pystray 调用 action 时会把 icon 作为第一个位置参数传入，
                    # 因此这里用 *_ 吃掉该参数，只用闭包捕获的索引 i 触发切换，
                    # 否则 i 会被 icon 对象覆盖导致 _toggle_pet 索引校验失败（静默无效）。
                    lambda *_args, i=i: self._on_toggle(i),
                    checked=lambda item, i=i: self.pets[i].visible,
                )
            )
        # 全局暂停 / 恢复（文案随状态变化）
        items.append(pystray.MenuItem(
            text=lambda item: '恢复全部' if self._is_paused() else '暂停全部',
            action=lambda *_args: self._on_pause(),
        ))
        items.append(pystray.MenuItem('显示全部', lambda *_args: self._on_show_all()))
        items.append(pystray.MenuItem('隐藏全部', lambda *_args: self._on_hide_all()))
        items.append(pystray.MenuItem('戳一下', lambda *_args: self._on_poke()))
        items.append(pystray.MenuItem('设置…', lambda *_args: self._on_settings()))
        items.append(pystray.MenuItem('关于', lambda *_args: self._on_about()))
        items.append(pystray.MenuItem('退出', self._on_quit))
        return pystray.Menu(*items)

    def _on_toggle(self, idx):
        """菜单点击切换人物显隐（在 pystray 后台线程中调用，经回调调度到主线程）。"""
        if self.on_toggle:
            self.on_toggle(idx)

    def _on_show_all(self, *args):
        if self.on_show_all:
            self.on_show_all()

    def _on_hide_all(self, *args):
        if self.on_hide_all:
            self.on_hide_all()

    def _on_poke(self, *args):
        if self.on_poke:
            self.on_poke()

    def _on_quit(self, icon=None, item=None):
        """菜单点击退出。"""
        if self.on_quit:
            self.on_quit()

    def start(self):
        """在后台守护线程启动托盘图标（run_detached 不阻塞主线程）。"""
        try:
            image = make_tray_icon_image(64)
            self.icon = pystray.Icon(
                "mate_paw",
                image,
                "桌面宠物 🐵",
                menu=self._build_menu(),
            )
            # run_detached：在守护线程中运行消息循环，立即返回，不阻塞 tkinter 主线程
            self.icon.run_detached()
            log.info("[Tray] pystray tray icon started")
        except Exception as e:
            log.error(f"[Tray] ERROR starting pystray tray: {e}")

    def stop(self):
        """停止托盘图标并从通知区域移除。"""
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
        log.info("[Tray] Tray stopped")


# ============================================================
# 宠物类
# ============================================================
_FONT_CACHE = {}


def load_cjk_font(size):
    """加载一个能正确渲染中文的字体（带缓存）。

    PIL 默认位图字体只支持 Latin，渲染中文会变成方块。这里优先找系统
    自带的中文字体（msyh/simhei/simsun 等），找不到再退回默认字体。
    """
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/malgun.ttf",
    ]
    font = None
    for p in candidates:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                break
            except Exception:
                continue
    if font is None:
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except Exception:
            font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font

# ============================================================
# 渲染缓存（A. 性能与渲染）
# ============================================================
class SpriteCache:
    """按 (group, frame, facing) 惰性缓存「翻转后的 PIL」与「ImageTk.PhotoImage」。

    旧实现每帧都对精灵做 FLIP_LEFT_RIGHT + LANCZOS 缩放 + 新建 PhotoImage，
    30fps × 多只宠物下 CPU 开销显著。这里把「朝向翻转」与「Tcl 图片对象」都缓存起来：
      - 翻转 PIL 只算一次（_flip）；
      - 最终显示的 PhotoImage 按 LRU 上限缓存（_photos），命中即返回同一对象，
        避免每帧重建 Tcl 图片。
    PhotoImage 一旦被 self.photo 引用就不会被 Tk 释放，所以 LRU 淘汰只会丢弃
    「当前没在显示」的条目，不会造成画面闪烁/空白。
    """

    def __init__(self, pose_groups, photo_cache_max=384):
        self.pose_groups = pose_groups          # name -> [PIL.Image, ...]
        self.max = max(1, int(photo_cache_max))
        self._flip = {}                         # (group, frame) -> 翻转后的 PIL
        self._photos = OrderedDict()            # (group, frame, facing) -> PhotoImage

    def get(self, group, frame, facing):
        """返回 (group, frame, facing) 对应的 PhotoImage；命中缓存则直接复用。"""
        key = (group, frame, facing)
        ph = self._photos.get(key)
        if ph is not None:
            self._photos.move_to_end(key)
            return ph
        base = self.pose_groups[group][frame]
        if not facing:
            fk = (group, frame)
            f = self._flip.get(fk)
            if f is None:
                f = base.transpose(Image.FLIP_LEFT_RIGHT)
                self._flip[fk] = f
            base = f
        ph = ImageTk.PhotoImage(base)
        self._photos[key] = ph
        self._photos.move_to_end(key)
        # LRU 淘汰：超出上限时丢弃最久未用的（当前显示的条目由 self.photo 保活）
        while len(self._photos) > self.max:
            self._photos.popitem(last=False)
        return ph


class MatePaw:
    def __init__(self, canvas, char_dir, char_id, label, screen_w, screen_h):
        self.canvas = canvas
        self.char_id = char_id
        self.label = label
        self.screen_w = screen_w
        self.screen_h = screen_h

        # 加载动作姿态：
        #   - 目录下的图片文件 = 单帧姿态，组名取文件名（如 foo.png -> 组 "foo"）
        #   - 子目录 = 多帧姿态，组名取目录名，目录内图片按文件名排序为帧序列
        # 组织成「命名姿态组」后：① 向后兼容旧资源（顶层多张图 = 多个组，右键循环）；
        # ② 不同行为状态可映射到同名组（walk/idle/look/...），让行为有不同动画。
        self.pose_groups = {}     # name -> [PIL.Image, ...]（已缩放 RGBA）
        self.pose_order = []      # 保持加载顺序的组名列表
        self.frame_index = 0      # 当前组内的帧序号
        self._frame_accum = 0     # 帧动画计时累加器
        try:
            entries = sorted(os.listdir(char_dir))
        except OSError:
            entries = []
        for name in entries:
            p = os.path.join(char_dir, name)
            try:
                ext = os.path.splitext(name)[1].lower()
                if os.path.isfile(p) and ext in IMAGE_EXTS:
                    self._add_group(os.path.splitext(name)[0], [self._load_sprite(p)])
                elif os.path.isdir(p):
                    frames = [self._load_sprite(os.path.join(p, fn))
                              for fn in sorted(os.listdir(p))
                              if os.path.splitext(fn)[1].lower() in IMAGE_EXTS]
                    if frames:
                        self._add_group(name, frames)
            except Exception as e:
                log.warning(f"[Pet {char_id}] 跳过无法加载的条目 {name}: {e}")
        if not self.pose_groups:
            raise RuntimeError(f"人物目录中没有任何可用图片: {char_dir}")
        self.pose_index = 0
        self.pose_count = len(self.pose_order)
        self._transient = {'group': None, 'until': 0.0}  # 被交互触发的瞬时表情
        # 渲染缓存：按 (group,frame,facing) 复用 PhotoImage，免去每帧重建
        self._cache = SpriteCache(self.pose_groups, PHOTO_CACHE_MAX)
        self._last_render_key = None   # 上一次实际切换的渲染键，用于跳过无变化的重建

        margin = 120
        self.x = random.randint(margin, max(margin, screen_w - SPRITE_W - margin))
        self.y = random.randint(margin, max(margin, screen_h - SPRITE_H - margin))
        speed = random.uniform(CRAWL_SPEED_MIN, CRAWL_SPEED_MAX)
        angle = random.uniform(0, 2 * math.pi)
        self.vx = speed * math.cos(angle)
        self.vy = speed * math.sin(angle)

        self.bob_phase = random.uniform(0, 2 * math.pi)
        self.facing_right = self.vx > 0
        self.state = 'crawling'
        self.state_timer = 0
        self.state_duration = 0
        # 防连发冷却状态：刚结束的动作先安静爬行一段时间，且同一动作在窗口内禁止重复
        self._last_action = None        # 上一个触发的瞬时动作（turn 不入）
        self._repeat_block = 0          # 该动作禁止重复的剩余帧数
        self._action_gap = 0            # 强制安静爬行（不触发任何动作）的剩余帧数
        # 朝向翻转冷却（F：避免精灵一秒内多次左右镜像）
        self._facing_cooldown = 0       # 距离下次允许翻转的剩余帧数
        self.dragging = False
        self.visible = True
        self.cursor_x = None       # 由主循环每帧写入的鼠标屏幕 x（看向光标用）

        self.photo = ImageTk.PhotoImage(self._current_frame())
        self.img_id = canvas.create_image(
            self.x + SPRITE_W // 2, self.y + SPRITE_H // 2,
            image=self.photo, anchor='center', tags='pet'
        )

        # 气泡对话图层（默认隐藏，喊"爸！"等时显示）
        self.bubble_id = canvas.create_image(0, 0, state='hidden', anchor='center')
        self.bubble_until = 0.0          # 气泡消失的时间戳（time.time()）
        self.bubble_photo = None         # 当前气泡的 PhotoImage（需持有引用防 GC）
        self.bubble_w = 0
        self.bubble_h = 0

    def update(self, paused=False):
        try:
            if not self.visible:
                self.canvas.itemconfig(self.img_id, state='hidden')
                self.canvas.itemconfig(self.bubble_id, state='hidden')
                return
            self.canvas.itemconfig(self.img_id, state='normal')

            if self.dragging:
                self._render()
                return

            if paused:
                self.bob_phase += BOB_SPEED
                self._render()
                return

            self.state_timer += 1
            if self.state == 'crawling':
                # 防连发冷却：
                #  - _repeat_block：上一动作禁止重复的剩余帧数，每帧递减；
                #  - _action_gap：刚结束动作后强制安静爬行、不触发任何动作的剩余帧数。
                # 冷却期内不掷骰，避免"左右张望"之类被连续触发导致刷新过快。
                if self._repeat_block > 0:
                    self._repeat_block -= 1
                if self._action_gap > 0:
                    self._action_gap -= 1
                    action = None
                else:
                    exclude = self._last_action if self._repeat_block > 0 else None
                    action = choose_crawl_action(
                        random.random(), PAUSE_CHANCE, LOOK_CHANCE, DIR_CHANGE_CHANCE,
                        IDLE_CHANCE, SLEEP_CHANCE, WAVE_CHANCE, BLINK_CHANCE,
                        exclude=exclude,
                    )
                if action == 'pause':
                    self._enter_state('pausing', PAUSE_DURATION)
                    self._register_action('pause')
                elif action == 'look':
                    self._enter_state('looking', LOOK_DURATION)
                    self._register_action('look')
                elif action == 'turn':
                    self._random_turn()
                    self._register_action('turn', transient=False)
                elif action == 'idle':
                    self._enter_state('idle', IDLE_DURATION)
                    self._register_action('idle')
                elif action == 'sleep':
                    self._enter_state('sleep', SLEEP_DURATION)
                    self._register_action('sleep')
                elif action == 'wave':
                    self._enter_state('wave', WAVE_DURATION)
                    self._register_action('wave')
                elif action == 'blink':
                    self._enter_state('blink', BLINK_DURATION)
                    self._register_action('blink')
                self._move()
            elif self.state in ('pausing', 'looking', 'idle', 'sleep', 'wave', 'blink'):
                if self.state_timer >= self.state_duration:
                    self._enter_state('crawling')

            # 空闲张望时看向光标（若开启且能取到光标位置）
            if self.state == 'looking' and FOLLOW_CURSOR and self.cursor_x is not None:
                # 同样带死区+冷却：光标几乎正上方时不翻，避免宠物在光标下方微移时左右闪烁
                pet_cx = self.x + SPRITE_W / 2
                self._set_facing(
                    facing_toward(pet_cx, self.cursor_x),
                    clear=abs(self.cursor_x - pet_cx) >= FACING_CURSOR_THRESHOLD,
                )

            # 空闲随机气泡（D）：当前没有气泡显示时才按概率冒一句
            if IDLE_BUBBLE_CHANCE > 0 and self.bubble_until < time.time():
                if random.random() < IDLE_BUBBLE_CHANCE:
                    self.say(pick_phrase(CONFIG.bubble_lines))

            self.bob_phase += BOB_SPEED
            self._advance_frame()
            self._render()
        except Exception as e:
            log.error(f"[Pet {self.label}] update error: {e}")

    def _move(self):
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2) or 1.0
        nx = self.x + self.vx
        ny = self.y + self.vy

        if nx <= 0:
            nx = 0; self.vx = abs(self.vx)
        elif nx >= self.screen_w - SPRITE_W:
            nx = self.screen_w - SPRITE_W; self.vx = -abs(self.vx)
        if ny <= 0:
            ny = 0; self.vy = abs(self.vy)
        elif ny >= self.screen_h - SPRITE_H:
            ny = self.screen_h - SPRITE_H; self.vy = -abs(self.vy)

        if self._hits_window(nx, ny):
            speed = max(speed, CRAWL_SPEED_MIN)
            cur = math.atan2(self.vy, self.vx)
            placed = False
            # 优先沿「当前朝向附近」找可行方向（保持行进方向稳定、减少左右翻转），
            # 角度范围逐步放宽；仅在被窗口完全围死时才全随机脱困。
            for spread in (math.pi / 6, math.pi / 3, math.pi / 2, math.pi):
                for _ in range(6):
                    ang = cur + random.uniform(-spread, spread)
                    tx = min(max(self.x + speed * math.cos(ang), 0), self.screen_w - SPRITE_W)
                    ty = min(max(self.y + speed * math.sin(ang), 0), self.screen_h - SPRITE_H)
                    if not self._hits_window(tx, ty):
                        nx, ny = tx, ty
                        self.vx = speed * math.cos(ang)
                        self.vy = speed * math.sin(ang)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                self._random_turn(full=True)

        self.x, self.y = nx, ny
        # 朝向更新带阈值死区 + 冷却（F）：|vx| 过小（近垂直）不翻，
        # 且两次翻转间至少隔 FACING_FLIP_COOLDOWN 帧，杜绝高频镜像闪烁。
        self._set_facing(self.vx > 0, clear=abs(self.vx) >= FACING_VX_THRESHOLD)

    def _enter_state(self, state, duration_range=None):
        self.state = state
        self.state_timer = 0
        if duration_range:
            lo, hi = duration_range
            self.state_duration = random.randint(lo, hi)
        # 行为状态 -> 命名姿态组（资源里没有对应组则 no-op，保持当前姿态）
        if state in STATE_POSE:
            self.set_pose_group(STATE_POSE[state])
        if state == 'crawling':
            speed = random.uniform(CRAWL_SPEED_MIN, CRAWL_SPEED_MAX)
            angle = random.uniform(0, 2 * math.pi)
            self.vx = speed * math.cos(angle)
            self.vy = speed * math.sin(angle)

    def _random_turn(self, full=False, max_delta=math.pi / 3):
        """转向：在**当前朝向附近**做小幅偏转，而不是瞬间随机到全新方向。

        爬行中的人物因此是「自然游走」，左右换向频率大幅下降，避免精灵频繁
        翻转刷新（这是之前观感差的根因之一）。
        仅当被窗口卡死（full=True，需要强行脱困）时才使用全随机方向。
        """
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2) or CRAWL_SPEED_MIN
        speed = max(CRAWL_SPEED_MIN, min(CRAWL_SPEED_MAX, speed))
        if full:
            angle = random.uniform(0, 2 * math.pi)
        else:
            cur = math.atan2(self.vy, self.vx)
            angle = cur + random.uniform(-max_delta, max_delta)
        self.vx = speed * math.cos(angle)
        self.vy = speed * math.sin(angle)

    def _register_action(self, action, transient=True):
        """登记一次触发的动作，用于防连发冷却。

        transient=True（进入有持续时间的姿态状态：looking/pausing/idle/...）：
          记为上一动作，并在 ACTION_REPEAT_BLOCK 帧内禁止重复触发；同时强制
          ACTION_GAP 帧的"安静爬行"间隔，避免动作连发、刷新过快。
        transient=False（turn 瞬时转向）：不参与冷却，避免频繁转向抑制其它行为。
        """
        if transient:
            self._last_action = action
            self._repeat_block = ACTION_REPEAT_BLOCK
            self._action_gap = ACTION_GAP

    def _set_facing(self, want_right, clear=False):
        """带迟滞与冷却的朝向更新，避免精灵一秒内多次左右镜像导致观感差。

        want_right: 期望朝向（True=朝右）。
        clear: 是否有「明确方向信号」。为 False 时进入死区——保持当前朝向，
            用于水平速度过小（近垂直运动）或光标距宠物过近等无明确方向场景。
        朝向真正改变后进入 FACING_FLIP_COOLDOWN 帧冷却，期间禁止再翻，
        保证最低翻转间隔（30fps、cooldown=15 时每秒最多 2 次）。
        """
        if self._facing_cooldown > 0:
            self._facing_cooldown -= 1
            return
        if not clear:
            return  # 无明确方向，保持当前朝向（迟滞死区）
        if bool(want_right) != self.facing_right:
            self.facing_right = bool(want_right)
            self._facing_cooldown = FACING_FLIP_COOLDOWN

    def _hits_window(self, x, y):
        pet_rect = (x, y, x + SPRITE_W, y + SPRITE_H)
        for wr in get_window_rects():
            if rects_overlap(pet_rect, wr):
                return True
        return False

    def _add_group(self, name, frames):
        """登记一个命名姿态组（同名只保留第一份，避免顶层文件与子目录重名冲突）。"""
        if name not in self.pose_groups and frames:
            self.pose_groups[name] = frames
            self.pose_order.append(name)

    def set_pose_group(self, name):
        """切到名为 name 的姿态组（从头帧开始）；不存在则保持当前（向后兼容）。"""
        if name and name in self.pose_groups:
            idx = self.pose_order.index(name)
            if idx != self.pose_index:
                self.pose_index = idx
                self.frame_index = 0

    def current_group_name(self):
        """当前应显示的姿态组名：瞬时反应优先，否则取当前 pose_index 对应组。"""
        if self._transient['until'] and time.time() < self._transient['until']:
            g = self._transient['group']
            if g in self.pose_groups:
                return g
        return self.pose_order[self.pose_index]

    def _current_frame(self):
        group = self.current_group_name()
        frames = self.pose_groups[group]
        return frames[self.frame_index % len(frames)]

    def react(self, kind):
        """被交互触发的瞬时表情：kind 对应 REACTION 表的组名 + 持续时间(ms)。
        资源里没有对应组时退化为保持当前姿态（仅气泡/逻辑生效，不影响行为）。"""
        spec = self.REACTION.get(kind)
        if not spec:
            return
        group, ms = spec
        self._transient = {'group': group, 'until': time.time() + ms / 1000.0}

    # 被交互触发的瞬时表情：组名 -> (姿态组, 持续毫秒)
    REACTION = {
        'shock': ('shock', 600),
        'happy': ('happy', 1200),
        'love': ('love', 1200),
    }

    def next_pose(self):
        if self.pose_count > 1:
            self.pose_index = (self.pose_index + 1) % self.pose_count
            self.frame_index = 0  # 切换姿态从头帧开始

    def set_visible(self, v):
        self.visible = v
        if not v:
            self.canvas.itemconfig(self.img_id, state='hidden')

    def _load_sprite(self, path):
        """加载单张精灵：转 RGBA -> 色键去背景 -> 缩放到标准尺寸。"""
        img = Image.open(path).convert('RGBA')
        img = chroma_key(img)
        return img.resize((SPRITE_W, SPRITE_H), Image.LANCZOS)

    def _advance_frame(self):
        """推进当前姿态内的动画帧（多帧姿态才动；单帧姿态不动）。"""
        frames = self.pose_groups[self.current_group_name()]
        if len(frames) <= 1:
            return
        anim_step = max(2, FPS // 8)  # 约 8fps 的动画速度
        self._frame_accum += 1
        if self._frame_accum >= anim_step:
            self._frame_accum = 0
            self.frame_index = (self.frame_index + 1) % len(frames)

    def _render(self):
        """把当前帧绘制到画布。

        性能关键路径（A）：仅在「渲染键」(group,frame,facing) 变化时才通过缓存
        重建 PhotoImage；宠物移动只更新坐标（便宜），朝向/帧动画/姿态切换才触发
        重建。旧实现每帧都做翻转 + LANCZOS 缩放 + 新建 PhotoImage，这里全部消除。
        """
        group = self.current_group_name()
        frames = self.pose_groups[group]
        frame = self.frame_index % len(frames)
        key = (group, frame, self.facing_right)
        if key != self._last_render_key:
            self.photo = self._cache.get(group, frame, self.facing_right)
            self.canvas.itemconfig(self.img_id, image=self.photo)
            self._last_render_key = key

        # 上下 bob 浮动（保留轻微「呼吸」动感，但不缩放图片，零额外像素运算）
        bob_y = int(math.sin(self.bob_phase) * BOB_AMP)
        cx = self.x + SPRITE_W // 2
        cy = self.y + SPRITE_H // 2 + bob_y
        self.canvas.coords(self.img_id, cx, cy)
        self._update_bubble()

    def say(self, text, duration_ms=BUBBLE_DURATION_MS):
        """弹出气泡对话（如喊"爸！"）。duration_ms 毫秒后自动消失。"""
        try:
            img, w, h = self._build_bubble(text)
            self.bubble_photo = ImageTk.PhotoImage(img)
            self.bubble_w = w
            self.bubble_h = h
            self.bubble_until = time.time() + duration_ms / 1000.0
            self.canvas.itemconfig(self.bubble_id, image=self.bubble_photo)
        except Exception as e:
            log.error(f"[Pet {self.label}] say error: {e}")

    def _build_bubble(self, text):
        """用 PIL 现画一个白色圆角气泡 + 朝下小尾巴 + 居中文字，返回 (img, w, h)。"""
        font = load_cjk_font(BUBBLE_FONT_SIZE)
        pad_x, pad_y = 22, 14
        # 先用临时画布测量文字尺寸
        tmp = Image.new('RGBA', (4, 4))
        d = ImageDraw.Draw(tmp)
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        w = tw + pad_x * 2
        h = th + pad_y * 2
        tail = 16  # 尾巴高度
        img = Image.new('RGBA', (w, h + tail), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # 气泡主体（圆角矩形）
        d.rounded_rectangle([0, 0, w, h], radius=min(22, h // 3),
                            fill=(255, 255, 255, 248),
                            outline=(70, 70, 70, 255), width=3)
        # 朝下的小尾巴：用与主体同色填充，顺带遮住底部轮廓在尾巴宽度内的横线
        cx = w // 2
        d.polygon([(cx - 13, h - 1), (cx + 13, h - 1), (cx, h + tail)],
                  fill=(255, 255, 255, 248))
        # 文字（用 textbbox 左上偏移对齐，避免默认基线导致文字偏上）
        d.text((pad_x - bbox[0], pad_y - bbox[1]), text, font=font,
               fill=(25, 25, 25, 255))
        return img, w, h + tail

    def _update_bubble(self):
        """每帧调用：根据时间戳和可见性决定气泡是否显示，并跟随宠物定位。"""
        active = (self.bubble_until and time.time() < self.bubble_until
                  and self.visible and self.bubble_photo)
        if not active:
            self.canvas.itemconfig(self.bubble_id, state='hidden')
            return
        bx = self.x + SPRITE_W // 2
        # 默认浮在头顶上方；太靠近屏幕顶部则改到身体下方
        top_y = self.y - self.bubble_h // 2 - 10
        if top_y < self.bubble_h // 2 + 4:
            by = self.y + SPRITE_H + self.bubble_h // 2 + 10
        else:
            by = top_y
        by = min(by, self.screen_h - self.bubble_h // 2 - 4)
        self.canvas.itemconfig(self.bubble_id, state='normal')
        self.canvas.coords(self.bubble_id, bx, by)



# ============================================================
# 主应用
# ============================================================
class MatePawApp:
    WINDOW_TITLE = 'mate_paw'

    def __init__(self):
        self.root = tk.Tk()
        self.screen_w, self.screen_h = get_screen_size()
        self.mouse_q = queue.Queue()
        self.drag = None
        self._hook = None
        self.tray = None
        self.hwnd = None  # 主窗口句柄，用于 SetWindowRgn
        self._region_sig = None  # 窗口可点区域签名缓存（未变则跳过 SetWindowRgn）
        self.paused = False  # 全局暂停：宠物停止爬行但保持显示/呼吸
        self.state_path = state_path()  # 状态持久化文件路径
        # 鼠标钩子内用于跟踪是否吞掉右键事件（仅由钩子线程读写，避免竞态）
        self._r_block = False

        self._setup_window()
        self._create_canvas()
        self._bind_canvas_events()  # canvas 事件绑定（替代钩子处理左键拖动）
        self._load_pets()
        self._setup_tray_icon()   # 原生 win32 托盘图标

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind('<Escape>', lambda e: self._on_close())

        # 全局鼠标钩子（仅用于屏蔽右键系统菜单；左键拖动走 canvas + SetWindowRgn）
        self._hook, self._hook_thread, self._hook_proc_cb = install_mouse_hook(self._hook_proc_impl)

        self._animate()

    def _setup_window(self):
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', '#f0f0f0')
        self.root.geometry(f'{self.screen_w}x{self.screen_h}+0+0')
        self.root.config(bg='#f0f0f0')
        self.root.title(self.WINDOW_TITLE)

        self.root.update_idletasks()
        hwnd = find_pet_window(self.WINDOW_TITLE)
        self.hwnd = hwnd
        if hwnd:
            try:
                # 不加 WS_EX_TRANSPARENT：之前用 WH_MOUSE_LL 钩子吞掉 LBUTTONDOWN 会让 Windows
                # 进入"按键未释放"状态，导致下一次点击不再产生事件（卡死）。
                # 现在改用 SetWindowRgn 把窗口限制为宠物矩形 —— 区域外点击直接穿透到桌面，
                # 区域内由 canvas 事件处理拖动。
                set_layered_tool_window(hwnd)
            except Exception as e:
                log.warning(f"Warning: style: {e}")
        # 初始 region：根据可见宠物集合随时更新
        self._update_window_region()

    def _update_window_region(self):
        """把窗口的可点击区域限制为可见宠物矩形的并集。
        区域之外的鼠标事件直接穿透到桌面 —— 这是替代 WS_EX_TRANSPARENT 的"局部可点"方案，
        与钩子吞事件不同，它会让 Windows 正确收到鼠标释放消息，避免卡死。
        SetWindowRgn 接管传入 region 的所有权，下次调用或销毁窗口时会自动释放。
        拖动期间由 _set_window_region_fullscreen 接管，本方法不会再被调用。

        性能（A）：多数帧宠物并未移动/显隐变化，此时矩形并集签名不变，直接跳过
        set_window_region（一次 win32 系统调用），避免每帧空转 syscall。
        """
        if not self.hwnd or self.drag:
            return
        try:
            rects = compute_pet_rects(self.pets, self.screen_w, self.screen_h)
            sig = tuple(rects)
            if sig == self._region_sig:
                return
            self._region_sig = sig
            set_window_region(self.hwnd, rects)
        except Exception:
            # 失败回退到全屏 region（不损失功能，但点击可能落到桌面图标）
            self._set_window_region_fullscreen()

    def _set_window_region_fullscreen(self):
        """拖动期间调用：把 region 临时设为全屏，保证鼠标在屏幕任意位置
        移动都能触发 canvas 的 <B1-Motion>。"""
        if not self.hwnd:
            return
        try:
            set_window_region_fullscreen(self.hwnd, self.screen_w, self.screen_h)
        except Exception:
            pass

    def _bind_canvas_events(self):
        """在 canvas 上绑定宠物拖动/释放/右键事件 —— 替代之前依赖鼠标钩子的方案。"""
        # 按下：在宠物 canvas item 上命中时触发；命中后 grab_set，使后续
        # Motion 即使鼠标离开宠物区域也能继续路由到 canvas
        self.canvas.tag_bind('pet', '<ButtonPress-1>', self._on_canvas_btn1_press)
        # 拖动 / 释放：绑在 canvas 上而不是 tag 上，确保即使宠物跟随鼠标移动，事件仍能继续被处理
        self.canvas.bind('<B1-Motion>', self._on_canvas_btn1_motion)
        self.canvas.bind('<ButtonRelease-1>', self._on_canvas_btn1_release)
        # 右键点宠物（在钩子吞掉事件之外的兜底，避免极少数情形还能看到系统菜单）
        self.canvas.tag_bind('pet', '<ButtonPress-3>', self._on_canvas_btn3_press)
        # 双击人物：宠物喊"爸！"弹气泡（canvas 级绑定，不受拖动 grab 影响）
        self.canvas.bind('<Double-Button-1>', self._on_canvas_btn1_double)

    def _on_canvas_btn1_press(self, event):
        pet = self._pet_at(event.x_root, event.y_root)
        if not pet:
            return
        # 记录按下信息，用于区分「轻点抚摸」与「拖拽」
        self.drag = {
            'pet': pet,
            'ox': event.x_root - pet.x, 'oy': event.y_root - pet.y,
            'start_x': event.x_root, 'start_y': event.y_root,
            'start_t': time.time(),
        }
        pet.dragging = True
        pet.react('shock')  # 被抓住时受惊一下（资源有 shock 组才可见，否则仅逻辑生效）
        # 拖动期间 region 切到全屏，否则宠物跟随鼠标离开原区域后收不到后续事件
        self._set_window_region_fullscreen()
        try:
            self.canvas.grab_set()
        except Exception:
            pass
        return 'break'

    def _on_canvas_btn1_motion(self, event):
        if not self.drag:
            return
        pet = self.drag['pet']
        pet.x = min(max(event.x_root - self.drag['ox'], 0), self.screen_w - SPRITE_W)
        pet.y = min(max(event.y_root - self.drag['oy'], 0), self.screen_h - SPRITE_H)

    def _on_canvas_btn1_release(self, event):
        if not self.drag:
            return
        pet = self.drag['pet']
        d = self.drag
        pet.dragging = False
        self.drag = None
        try:
            self.canvas.grab_release()
        except Exception:
            pass
        # 拖动结束，恢复成"只覆盖宠物矩形"的 region（外面点击重新穿透到桌面）
        self._update_window_region()
        # 区分轻点与拖拽：位移小且短 -> 抚摸反应 + 气泡；否则是成功拖拽 -> 放下开心
        dx = event.x_root - d['start_x']
        dy = event.y_root - d['start_y']
        dt_ms = (time.time() - d['start_t']) * 1000.0
        if is_tap(dx, dy, dt_ms) and TAP_REACT:
            pet.react('happy')
            pet.say(pick_phrase(CONFIG.bubble_lines))
        else:
            pet.react('happy')
        self._save_state()

    def _on_canvas_btn3_press(self, event):
        pet = self._pet_at(event.x_root, event.y_root)
        if pet:
            pet.next_pose()
            self._save_state()
        return 'break'  # 阻止 canvas 把事件传到别处（在我们的 SetWindowRgn 方案里这层通常不会触发）

    def _on_canvas_btn1_double(self, event):
        pet = self._pet_at(event.x_root, event.y_root)
        if pet:
            pet.react('happy')
            pet.say("爸！")
        return 'break'



    def _create_canvas(self):
        self.canvas = tk.Canvas(self.root, width=self.screen_w, height=self.screen_h,
                                bg='#f0f0f0', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def _load_pets(self):
        self.pets = []
        self._state = self._load_state()
        res_dir = get_res_dir()

        if not os.path.isdir(res_dir):
            log.warning(f"[Pet] 未找到 res 资源目录: {res_dir}")
            log.warning("[Pet] 请在程序运行文件夹下创建 res 目录，并在其中为每个"
                        "人物建立一个子文件夹（文件夹名即人物 id），子文件夹内存放该人物的所有动作姿态图片。")
            return

        # res 下每个子文件夹即一个人物，文件夹名即人物 id
        char_ids = sorted(
            d for d in os.listdir(res_dir)
            if os.path.isdir(os.path.join(res_dir, d))
        )
        if not char_ids:
            log.warning(f"[Pet] res 目录下没有找到任何人物文件夹: {res_dir}")
            return

        for cid in char_ids:
            char_dir = os.path.join(res_dir, cid)
            try:
                pet = MatePaw(self.canvas, char_dir, cid, cid, self.screen_w, self.screen_h)
                # 恢复上次的位置 / 显隐 / 姿态
                st = self._state.get(cid)
                if st:
                    pet.x = min(max(int(st.get('x', pet.x)), 0), max(0, self.screen_w - SPRITE_W))
                    pet.y = min(max(int(st.get('y', pet.y)), 0), max(0, self.screen_h - SPRITE_H))
                    if 'visible' in st:
                        pet.set_visible(bool(st['visible']))
                    pi = int(st.get('pose_index', 0))
                    if 0 <= pi < pet.pose_count:
                        pet.pose_index = pi
                self.pets.append(pet)
                log.info(f"[Pet] 已加载人物 {cid}（共 {pet.pose_count} 个姿态）")
            except Exception as e:
                log.warning(f"[Pet] 跳过人物 {cid}: {e}")

    # ---- 系统托盘图标（pystray）----
    def _setup_tray_icon(self):
        """创建基于 pystray 的系统托盘图标，菜单含每人显隐开关 + 显示/隐藏全部 +
        戳一下 + 暂停/设置/关于 + 退出。"""
        try:
            self.tray = PystrayTrayIcon(
                pets=self.pets,
                on_quit_callback=lambda: self.root.after(0, self._on_close),
                on_toggle_callback=self._on_tray_toggle,
                on_pause_callback=lambda: self.root.after(0, self._toggle_pause_all),
                on_settings_callback=lambda: self.root.after(0, self._open_settings),
                on_about_callback=lambda: self.root.after(0, self._open_about),
                on_show_all_callback=lambda: self.root.after(0, self._show_all),
                on_hide_all_callback=lambda: self.root.after(0, self._hide_all),
                on_poke_callback=lambda: self.root.after(0, self._poke_all),
                get_paused_callback=lambda: self.paused,
            )
            self.tray.start()
        except Exception as e:
            log.error(f"[Tray] ERROR starting pystray tray: {e}")

    def _on_tray_toggle(self, idx):
        """托盘菜单切换人物显隐——从托盘线程调用，调度到主线程执行。"""
        self.root.after(0, lambda: self._toggle_pet(idx))

    def _toggle_pet(self, idx):
        """主线程中执行人物显隐切换。"""
        if 0 <= idx < len(self.pets):
            pet = self.pets[idx]
            pet.set_visible(not pet.visible)
            # 显隐变化后立即同步窗口可点区域（隐藏的宠物不应该再接住点击）
            self._update_window_region()
            self._save_state()

    def _load_state(self):
        """读取状态文件，返回 {char_id: {x,y,visible,pose_index}}。"""
        try:
            if os.path.isfile(self.state_path):
                with open(self.state_path, encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get('pets'), dict):
                    return data['pets']
        except Exception as e:
            log.warning("读取状态失败: %s", e)
        return {}

    def _save_state(self):
        """把每只宠物的位置/显隐/姿态写入状态文件。"""
        try:
            data = {
                "version": 1,
                "pets": {
                    p.char_id: {
                        "x": int(p.x), "y": int(p.y),
                        "visible": p.visible, "pose_index": p.pose_index,
                    } for p in self.pets
                },
            }
            with open(self.state_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error("保存状态失败: %s", e)

    def _toggle_pause_all(self):
        """托盘“暂停全部/恢复全部”触发：切换全局暂停标志。"""
        self.paused = not self.paused
        log.info("全局%s", "已暂停" if self.paused else "已恢复")

    def _apply_settings(self, cfg):
        """设置对话框“应用并保存”的回调：应用配置并落盘 config.json。"""
        try:
            set_config(cfg)
            path = default_config_path()
            cfg.save(path)
            log.info("设置已保存: %s", path)
        except Exception as e:
            log.error("保存设置失败: %s", e)

    def _open_settings(self):
        """打开设置对话框（主线程）。"""
        try:
            SettingsDialog(self.root, CONFIG, self._apply_settings)
        except Exception as e:
            log.error("打开设置失败: %s", e)

    def _open_about(self):
        """打开“关于”对话框（主线程）。"""
        try:
            AboutDialog(self.root)
        except Exception as e:
            log.error("打开关于失败: %s", e)

    # ---- 鼠标钩子 ----
    def _hook_proc_impl(self, nCode, wParam, lParam):
        """
        低级鼠标钩子（仅用于屏蔽右键系统菜单）。

        左键拖动现在由 canvas 事件 + SetWindowRgn 处理，不再通过此钩子吞事件。
        之所以这样设计：用钩子吞掉 LBUTTONDOWN 会让 Windows 进入"按钮未释放"
        状态，导致下一次点击不再产生事件（左键拖动卡死）。
        SetWindowRgn 把窗口限定在宠物矩形 → 区域内点击由 canvas 处理、区域外
        点击穿透到桌面 → 完全不需要吞事件，桌面就不会误触发框选/拖动。
        右键系统菜单只能靠钩子屏蔽（canvas tkinter 绑定无法阻止 Windows
        DefWindowProc 生成 WM_CONTEXTMENU），所以右键这里仍走吞事件路线。
        """
        if nCode >= 0:
            hs = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            x, y = hs.pt.x, hs.pt.y
            if wParam == WM_RBUTTONDOWN:
                pet = self._pet_at(x, y)
                if pet:
                    # 右键点中宠物：吞掉按下，避免桌面资源管理器显示系统右键菜单
                    self._r_block = True
                    self.mouse_q.put(('rdown', x, y))
                    return 1
            elif wParam == WM_RBUTTONUP:
                if self._r_block:
                    # 吞掉配套抬起，否则 DefWindowProc 会以按下位置弹出 WM_CONTEXTMENU
                    self._r_block = False
                    return 1
        return 0

    def _pet_at(self, x, y):
        pad = 18
        for pet in reversed(self.pets):
            if not pet.visible:
                continue
            if (pet.x + pad <= x <= pet.x + SPRITE_W - pad and
                    pet.y + pad <= y <= pet.y + SPRITE_H - pad):
                return pet
        return None

    def _handle_mouse(self, et, x, y):
        # 现在只剩下 'rdown'（左键拖动走 canvas 事件，不经过这里）
        if et == 'rdown':
            pet = self._pet_at(x, y)
            if pet:
                pet.next_pose()
                self._save_state()

    def _animate(self):
        try:
            while not self.mouse_q.empty():
                et, x, y = self.mouse_q.get_nowait()
                self._handle_mouse(et, x, y)
        except Exception:
            pass
        # 把光标屏幕 x 写入每只宠物（看向光标用）；无指针/不可取时置 None。
        # 仅在开启 FOLLOW_CURSOR 时才查询指针（一次 Tcl 调用），否则置 None 省开销。
        if FOLLOW_CURSOR:
            try:
                cx = self.root.winfo_pointerx()
            except Exception:
                cx = None
        else:
            cx = None
        for pet in self.pets:
            pet.cursor_x = cx if (cx is not None and cx >= 0) else None
        for pet in self.pets:
            pet.update(self.paused)
        # 让窗口 region 跟随可见宠物的位置一起移动（拖动中由 fullscreen 接管，会跳过）
        self._update_window_region()
        self.root.after(UPDATE_MS, self._animate)

    def _show_all(self):
        for pet in self.pets:
            pet.set_visible(True)
        self._update_window_region()
        self._save_state()

    def _hide_all(self):
        for pet in self.pets:
            pet.set_visible(False)
        self._update_window_region()
        self._save_state()

    def _poke_all(self):
        """戳一下全部宠物：受惊/开心反应 + 气泡。"""
        for pet in self.pets:
            if not pet.visible:
                continue
            pet.react('happy')
            pet.say(POKE_BUBBLE)

    def _on_close(self):
        # 退出前保存状态（位置/显隐/姿态），下次启动恢复
        try:
            self._save_state()
        except Exception:
            pass
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            if self._hook:
                uninstall_mouse_hook(self._hook)
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        log.info(f"[mate_paw] {len(self.pets)} pets on {self.screen_w}x{self.screen_h}")
        log.info("左键拖动 / 右键换姿态 / 双击喊爸爸 / 托盘图标开关人物 / Esc 退出")
        self.root.mainloop()


class SettingsDialog:
    """设置对话框：实时调节行为参数并落盘 config.json。"""

    # (标签, 配置键, 最小值, 最大值, 步进)
    SLIDERS = [
        ("爬行速度下限", "crawl_speed_min", 0.5, 8.0, 0.1),
        ("爬行速度上限", "crawl_speed_max", 0.5, 10.0, 0.1),
        ("暂停概率", "pause_chance", 0.0, 0.05, 0.001),
        ("张望概率", "look_chance", 0.0, 0.05, 0.001),
        ("转向概率", "dir_change_chance", 0.0, 0.05, 0.001),
        ("空闲概率", "idle_chance", 0.0, 0.01, 0.0001),
        ("睡觉概率", "sleep_chance", 0.0, 0.005, 0.0001),
        ("招手概率", "wave_chance", 0.0, 0.005, 0.0001),
        ("眨眼概率", "blink_chance", 0.0, 0.02, 0.0005),
        ("空闲气泡概率", "idle_bubble_chance", 0.0, 0.005, 0.0001),
        ("动作间隔冷却(帧)", "action_gap", 0, 120, 1),
        ("同动作冷却(帧)", "action_repeat_block", 0, 600, 5),
        ("气泡时长(ms)", "bubble_duration_ms", 800, 6000, 100),
    ]
    # (标签, 配置键)
    CHECKBOXES = [
        ("跟随光标（空闲张望时）", "follow_cursor"),
        ("点击抚摸反应", "tap_react"),
    ]
    LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]

    def __init__(self, parent, config, on_apply):
        self.config = config
        self.on_apply = on_apply
        self.win = tk.Toplevel(parent)
        self.win.title("mate-paw 设置")
        self.win.attributes('-topmost', True)
        self.win.resizable(False, False)
        self.vars = {}
        self._build()

    def _build(self):
        pad = {'padx': 8, 'pady': 4}
        for i, (label, key, lo, hi, step) in enumerate(self.SLIDERS):
            tk.Label(self.win, text=label).grid(row=i, column=0, sticky='w', **pad)
            var = tk.DoubleVar(value=float(self.config.get(key)))
            tk.Scale(self.win, variable=var, from_=lo, to=hi, resolution=step,
                     orient='horizontal', length=200).grid(row=i, column=1, **pad)
            self.vars[key] = var
        r = len(self.SLIDERS)
        # 复选框（跟随光标 / 点击抚摸）
        for j, (label, key) in enumerate(self.CHECKBOXES):
            var = tk.BooleanVar(value=bool(self.config.get(key, False)))
            cb = tk.Checkbutton(self.win, text=label, variable=var)
            cb.grid(row=r + j, column=0, columnspan=2, sticky='w', **pad)
            self.vars[key] = var
        r2 = r + len(self.CHECKBOXES)
        tk.Label(self.win, text="日志等级").grid(row=r2, column=0, sticky='w', **pad)
        lv = tk.StringVar(value=str(self.config.get('log_level', 'INFO')))
        tk.OptionMenu(self.win, lv, *self.LOG_LEVELS).grid(row=r2, column=1, sticky='w', **pad)
        self.vars['log_level'] = lv
        btn_row = r2 + 1
        tk.Button(self.win, text="应用并保存", command=self._do_apply).grid(row=btn_row, column=0, **pad)
        tk.Button(self.win, text="取消", command=self.win.destroy).grid(row=btn_row, column=1, **pad)

    def _collect(self):
        data = self.config.to_dict()
        for key, var in self.vars.items():
            if key == 'log_level':
                data[key] = var.get()
            else:
                val = var.get()
                if key in ('bubble_duration_ms', 'action_gap', 'action_repeat_block'):
                    val = int(round(val))
                data[key] = val
        return data

    def _do_apply(self):
        data = self._collect()
        cfg = Config(data)
        # 简单合理性校验：速度上限不低于下限
        if cfg.crawl_speed_max < cfg.crawl_speed_min:
            cfg.crawl_speed_max = cfg.crawl_speed_min
        self.on_apply(cfg)
        self.win.destroy()


class AboutDialog:
    """“关于”对话框。"""

    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.title("关于 mate-paw")
        self.win.attributes('-topmost', True)
        self.win.resizable(False, False)
        info = (
            f"mate-paw 桌面宠物  v{APP_VERSION}\n\n"
            "多只在桌面爬行的人形猴子，可拖动 / 右键换姿态 /\n"
            "双击喊爸爸 / 托盘开关人物。\n\n"
            "仓库: github.com/Genprox997/mate-paw"
        )
        tk.Label(self.win, text=info, justify='left', padx=12, pady=12).pack()
        tk.Button(self.win, text="关闭", command=self.win.destroy).pack(pady=(0, 12))


def self_check() -> int:
    """启动自检（无界面）：校验资源目录 / 字体 / 关键依赖。返回进程退出码。"""
    ok = True
    log.info(f"mate-paw v{APP_VERSION} 自检")
    res = get_res_dir()
    report = validate_res(res)
    if report['missing']:
        log.error(f"[FAIL] 未找到 res 目录: {res}")
        ok = False
    elif report['empty']:
        log.warning(f"[WARN] res 目录下没有任何人物文件夹: {res}")
    else:
        log.info(f"[OK] res 目录: {res}（{len(report['chars'])} 个人物）")
        for name, info in report['chars'].items():
            if info['ok']:
                log.info(f"[OK] 人物 {name}")
            else:
                ok = False
                log.error(f"[FAIL] 人物 {name}:")
                for iss in info['issues']:
                    log.error(f"      - {iss}")
    try:
        load_cjk_font(20)
        log.info("[OK] 中文字体可用")
    except Exception as e:
        log.warning(f"[WARN] 中文字体加载失败: {e}")
    for m in ("PIL", "win32gui", "pystray", "tkinter"):
        try:
            __import__(m)
            log.info(f"[OK] 依赖 {m}")
        except Exception as e:
            log.error(f"[FAIL] 依赖缺失 {m}: {e}")
            ok = False
    log.info("自检结果: %s", "通过" if ok else "存在问题")
    return 0 if ok else 1


if __name__ == '__main__':
    # 冻结的 GUI 模式（console=False）下 sys.stdout/stderr 可能为 None，
    # 此处兜底重定向到 devnull，避免任何 print() 调用抛异常。
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, 'w')
        if sys.stderr is None:
            sys.stderr = open(os.devnull, 'w')
    except Exception:
        pass
    args = sys.argv[1:]
    if "--version" in args:
        print(APP_VERSION)
        sys.exit(0)
    if "--check" in args:
        sys.exit(self_check())
    MatePawApp().run()
