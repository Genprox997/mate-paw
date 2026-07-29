"""
桌面宠物应用 - mate-paw (v5)
4 个"人形猴子"在桌面自由爬行玩耍，感知窗口边缘作为障碍物。
交互：
  - 鼠标左键拖动人物到其他位置
  - 鼠标右键人物切换姿态（爬行 / 坐姿 / 招手 循环）
  - 任务栏系统托盘图标（原生 win32gui）：每人显隐开关 + 退出
  - ESC 关闭程序
"""

import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
import win32gui
import win32con
import win32api
import random
import math
import os
import sys
import time
import queue
import threading
import ctypes
from ctypes import wintypes

# ============================================================
# 配置
# ============================================================
SPRITE_W = 180
SPRITE_H = 260
FPS = 30
UPDATE_MS = 1000 // FPS
BOB_AMP = 6
BOB_SPEED = 0.18
SCALE_RANGE = 0.025

# 支持的动作姿态图片格式
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff')

CRAWL_SPEED_MIN = 1.5
CRAWL_SPEED_MAX = 3.5
PAUSE_CHANCE = 0.006
LOOK_CHANCE = 0.004
PAUSE_DURATION = (40, 120)
LOOK_DURATION = (50, 150)
DIR_CHANGE_CHANCE = 0.012

# ============================================================
# 全局鼠标钩子 (ctypes)
# ============================================================
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205

user32 = ctypes.windll.user32


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

# ============================================================
# 工具函数
# ============================================================
def get_screen_size():
    return win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)


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
    # 未找到现成的 res，回退到 cwd/res 并交由调用方提示
    return os.path.join(os.getcwd(), 'res')


def remove_light_bg(im, threshold=248):
    """温和背景清除：只移除纯白/近白像素（RGB均>threshold），不伤人物内容"""
    if im.mode != 'RGBA':
        im = im.convert('RGBA')
    data = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = data[x, y]
            if int(r) > threshold and int(g) > threshold and int(b) > threshold:
                data[x, y] = (r, g, b, 0)
    return im


def get_window_rects(cache_ttl=2.0):
    now = time.time()
    cache = getattr(get_window_rects, '_cache', None)
    if cache is not None and now - get_window_rects._cache_time < cache_ttl:
        return cache

    screen_w = get_screen_size()[0]
    screen_h = get_screen_size()[1]
    our_title = 'mate_paw'
    rects = []

    def enum_cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title or title == our_title:
                return True
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            w, h = right - left, bottom - top
            if w < 80 or h < 60:
                return True
            if w >= 0.9 * screen_w and h >= 0.9 * screen_h:
                return True
            if (w >= 0.9 * screen_w and h <= 60) or (h >= 0.9 * screen_h and w <= 60):
                return True
            rects.append((left, top, right, bottom))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(enum_cb, None)
    get_window_rects._cache = rects
    get_window_rects._cache_time = now
    return rects


def rects_overlap(r1, r2):
    return not (r1[2] <= r2[0] or r1[0] >= r2[2] or r1[3] <= r2[1] or r1[1] >= r2[3])


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


def pil_to_hicon(image, size=48):
    """将 PIL Image 转换为 Windows HICON 句柄。通过保存临时 ICO 文件实现。"""
    import tempfile
    img = image.convert('RGBA').resize((size, size), Image.LANCZOS)
    # 注意：tempfile.mktemp 在 Python 3 下只返回单个 path 字符串（不解包成 tuple）。
    # 原代码 fd, path = tempfile.mktemp(...) 会抛 "too many values to unpack"，导致
    # 这里静默返回 None，托盘图标永远不被添加（这是 v5 托盘消失的根因）。
    # 用 mkstemp 拿一个真正的文件 fd，写完再关/删。
    fd, path = tempfile.mkstemp(suffix='.ico')
    try:
        try:
            import os as _os
            _os.close(fd)
        except Exception:
            pass
        img.save(path, format='ICO', sizes=[(size, size)])
        hicon = win32gui.LoadImage(
            0, path, win32con.IMAGE_ICON, size, size,
            win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        )
        return hicon
    except Exception:
        return None
    finally:
        try:
            import os as _os
            _os.remove(path)
        except Exception:
            pass


# ============================================================
# 原生 Win32 系统托盘图标（替代 pystray）
# ============================================================
class NativeTrayIcon:
    """使用纯 win32gui/win32api 实现的系统托盘图标，在冻结 exe 中稳定工作。"""

    WM_TRAY_CALLBACK = win32con.WM_USER + 1
    ID_TRAY_APP = 1000
    IDM_FIRST_TOGGLE = 2000
    IDM_QUIT = 2999

    def __init__(self, pets, on_quit_callback, on_toggle_callback=None):
        """
        pets: list of MatePaw 对象（需要有 .label 和 .visible 属性）
        on_quit_callback: 退出回调函数
        on_toggle_callback: 切换人物显隐的回调，参数为人物在 pets 列表中的索引
        """
        self.pets = pets
        self.on_quit = on_quit_callback
        self.on_toggle = on_toggle_callback
        self.hwnd = None
        self.hicon = None
        self.running = False
        self.thread = None
        self._lock = threading.Lock()

    def start(self):
        """在后台线程启动托盘图标和消息循环。"""
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="TrayThread")
        self.thread.start()
        print("[Tray] Native tray icon started")

    def stop(self):
        """停止托盘图标并清理资源。"""
        self.running = False
        if self.hwnd:
            try:
                self._remove_icon()
                win32gui.DestroyWindow(self.hwnd)
            except Exception:
                pass
            self.hwnd = None
        print("[Tray] Tray stopped")

    def _run_loop(self):
        """托盘线程主循环：创建隐藏窗口、添加图标、消息循环。"""
        try:
            # 1. 创建隐藏窗口类
            wc = win32gui.WNDCLASS()
            wc.lpszClassName = "MatePawTrayWnd"
            wc.lpfnWndProc = self._wnd_proc
            wc.hInstance = win32api.GetModuleHandle(None)

            class_atom = win32gui.RegisterClass(wc)

            # 2. 创建隐藏窗口
            self.hwnd = win32gui.CreateWindowEx(
                0, class_atom, "MatePaw Tray",
                0, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None
            )

            # 3. 创建并添加托盘图标
            icon_img = make_tray_icon_image(48)
            self.hicon = pil_to_hicon(icon_img, 48)
            if self.hicon:
                self._add_icon()

            # 4. 消息循环
            msg = wintypes.MSG()
            while self.running:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            # 清理
            if self.hwnd:
                self._remove_icon()
                win32gui.DestroyWindow(self.hwnd)
                self.hwnd = None

        except Exception as e:
            print(f"[Tray] Error in tray thread: {e}")

    def _wnd_proc(self, hwnd, msg, wParam, lParam):
        """隐藏窗口的消息处理函数。"""
        if msg == self.WM_TRAY_CALLBACK:
            if lParam == win32con.WM_RBUTTONUP or lParam == win32con.WM_LBUTTONUP:
                self._show_popup_menu()
            elif lParam == win32con.WM_LBUTTONDBLCLK:
                pass  # 双击可扩展功能
            return 0
        elif msg == win32con.WM_COMMAND:
            cmd_id = wParam & 0xFFFF
            if cmd_id == self.IDM_QUIT:
                self.on_quit()
            elif self.IDM_FIRST_TOGGLE <= cmd_id < self.IDM_QUIT:
                idx = cmd_id - self.IDM_FIRST_TOGGLE
                if self.on_toggle:
                    self.on_toggle(idx)
            return 0
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wParam, lParam)

    def _add_icon(self):
        """添加托盘图标到通知区域。"""
        nid = (
            self.hwnd,           # hwnd
            self.ID_TRAY_APP,    # uID
            win32con.NIF_ICON | win32con.NIF_MESSAGE | win32con.NIF_TIP,  # uFlags
            self.WM_TRAY_CALLBACK,  # uCallbackMessage
            self.hicon,          # hIcon
            "桌面宠物 🐵",       # szTip (tooltip)
        )
        # 使用 Shell_NotifyIconW (wide string version)
        nid_struct = self._make_notify_icon_data(nid)
        win32gui.Shell_NotifyIcon(win32con.NIM_ADD, nid_struct)

    def _remove_icon(self):
        """从通知区域移除托盘图标。"""
        nid = (self.hwnd, self.ID_TRAY_APP, 0, 0, 0, "")
        nid_struct = self._make_notify_icon_data(nid)
        win32gui.Shell_NotifyIcon(win32con.NIM_DELETE, nid_struct)

    @staticmethod
    def _make_notify_icon_data(nid):
        """构建 NOTIFYICONDATA 结构体用于 Shell_NotifyIcon。"""
        class NOTIFYICONDATA(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeout", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
            ]

        nid_data = NOTIFYICONDATA()
        nid_data.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid_data.hWnd = nid[0]
        nid_data.uID = nid[1]
        nid_data.uFlags = nid[2]
        nid_data.uCallbackMessage = nid[3]
        nid_data.hIcon = nid[4]
        tip = nid[5] if len(nid) > 5 else ""
        nid_data.szTip = tip[:127]
        return nid_data

    def _show_popup_menu(self):
        """显示右键弹出菜单（含每人显隐勾选 + 退出）。"""
        try:
            menu = win32gui.CreatePopupMenu()

            with self._lock:
                for i, pet in enumerate(self.pets):
                    label = pet.label
                    checked = pet.visible
                    flags = win32con.MF_STRING
                    if checked:
                        flags |= win32con.MF_CHECKED
                    else:
                        flags |= win32con.MF_UNCHECKED
                    win32gui.AppendMenu(menu, flags, self.IDM_FIRST_TOGGLE + i, label)

            # 分隔线
            win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")

            # 退出
            win32gui.AppendMenu(menu, win32con.MF_STRING, self.IDM_QUIT, "退出")

            # 显示菜单
            # 注意：使用 TPM_RETURNCMD 时，TrackPopupMenu 直接返回被选中项的 ID，
            # 不会向窗口发送 WM_COMMAND。因此必须在此处处理返回值，否则菜单点击无反应。
            pos = win32api.GetCursorPos()
            win32gui.SetForegroundWindow(self.hwnd)
            cmd = win32gui.TrackPopupMenu(
                menu,
                win32con.TPM_RIGHTBUTTON | win32con.TPM_RETURNCMD,
                pos[0], pos[1],
                0, self.hwnd, None
            )
            win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
            win32gui.DestroyMenu(menu)

            # 直接派发命令（通过回调调度到主线程执行，避免 tkinter 跨线程崩溃）
            if cmd == self.IDM_QUIT:
                self.on_quit()
            elif self.IDM_FIRST_TOGGLE <= cmd < self.IDM_QUIT:
                idx = cmd - self.IDM_FIRST_TOGGLE
                if self.on_toggle:
                    self.on_toggle(idx)

        except Exception as e:
            print(f"[Tray] Menu error: {e}")


# ============================================================
# 宠物类
# ============================================================
class MatePaw:
    def __init__(self, canvas, char_dir, char_id, label, screen_w, screen_h):
        self.canvas = canvas
        self.char_id = char_id
        self.label = label
        self.screen_w = screen_w
        self.screen_h = screen_h

        # 加载该人物目录下所有动作姿态（按文件名排序，第一个为默认姿态）
        self.pose_images = []
        try:
            file_names = sorted(
                f for f in os.listdir(char_dir)
                if os.path.splitext(f)[1].lower() in IMAGE_EXTS
            )
        except OSError:
            file_names = []
        for fn in file_names:
            p = os.path.join(char_dir, fn)
            if os.path.isfile(p):
                try:
                    img = Image.open(p).convert('RGBA')
                    img = remove_light_bg(img)
                    img = img.resize((SPRITE_W, SPRITE_H), Image.LANCZOS)
                    self.pose_images.append(img)
                except Exception as e:
                    print(f"[Pet {char_id}] 跳过无法加载的图片 {fn}: {e}")
        if not self.pose_images:
            raise RuntimeError(f"人物目录中没有任何可用图片: {char_dir}")
        self.pose_index = 0
        self.pose_count = len(self.pose_images)

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
        self.dragging = False
        self.visible = True

        self.photo = ImageTk.PhotoImage(self.pose_images[0])
        self.img_id = canvas.create_image(
            self.x + SPRITE_W // 2, self.y + SPRITE_H // 2,
            image=self.photo, anchor='center', tags='pet'
        )

    def update(self):
        try:
            if not self.visible:
                self.canvas.itemconfig(self.img_id, state='hidden')
                return
            self.canvas.itemconfig(self.img_id, state='normal')

            if self.dragging:
                self._render()
                return

            self.state_timer += 1
            if self.state == 'crawling':
                r = random.random()
                if r < PAUSE_CHANCE:
                    self._enter_state('pausing', PAUSE_DURATION)
                elif r < PAUSE_CHANCE + LOOK_CHANCE:
                    self._enter_state('looking', LOOK_DURATION)
                elif r < PAUSE_CHANCE + LOOK_CHANCE + DIR_CHANGE_CHANCE:
                    self._random_turn()
                self._move()
            elif self.state == 'pausing':
                if self.state_timer >= self.state_duration:
                    self._enter_state('crawling')
            elif self.state == 'looking':
                if self.state_timer >= self.state_duration:
                    self._enter_state('crawling')

            self.bob_phase += BOB_SPEED
            self._render()
        except Exception as e:
            print(f"[Pet {self.label}] update error: {e}")

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
            placed = False
            for _ in range(10):
                ang = random.uniform(0, 2 * math.pi)
                sp = max(speed, CRAWL_SPEED_MIN)
                tx = min(max(self.x + sp * math.cos(ang), 0), self.screen_w - SPRITE_W)
                ty = min(max(self.y + sp * math.sin(ang), 0), self.screen_h - SPRITE_H)
                if not self._hits_window(tx, ty):
                    nx, ny = tx, ty
                    self.vx = sp * math.cos(ang)
                    self.vy = sp * math.sin(ang)
                    placed = True
                    break
            if not placed:
                self._random_turn()

        self.x, self.y = nx, ny
        self.facing_right = self.vx > 0

    def _enter_state(self, state, duration_range=None):
        self.state = state
        self.state_timer = 0
        if duration_range:
            lo, hi = duration_range
            self.state_duration = random.randint(lo, hi)
        if state == 'crawling':
            speed = random.uniform(CRAWL_SPEED_MIN, CRAWL_SPEED_MAX)
            angle = random.uniform(0, 2 * math.pi)
            self.vx = speed * math.cos(angle)
            self.vy = speed * math.sin(angle)

    def _random_turn(self):
        angle = random.uniform(0, 2 * math.pi)
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        speed = max(CRAWL_SPEED_MIN, min(CRAWL_SPEED_MAX, speed))
        self.vx = speed * math.cos(angle)
        self.vy = speed * math.sin(angle)

    def _hits_window(self, x, y):
        pet_rect = (x, y, x + SPRITE_W, y + SPRITE_H)
        for wr in get_window_rects():
            if rects_overlap(pet_rect, wr):
                return True
        return False

    def next_pose(self):
        if self.pose_count > 1:
            self.pose_index = (self.pose_index + 1) % self.pose_count

    def set_visible(self, v):
        self.visible = v
        if not v:
            self.canvas.itemconfig(self.img_id, state='hidden')

    def _render(self):
        base = self.pose_images[self.pose_index]
        if self.facing_right:
            display = base.copy()
        else:
            display = base.transpose(Image.FLIP_LEFT_RIGHT)

        scale = 1.0 + SCALE_RANGE * math.sin(self.bob_phase * 0.5)
        new_w = max(1, int(display.width * scale))
        new_h = max(1, int(display.height * scale))
        display = display.resize((new_w, new_h), Image.LANCZOS)

        bob_y = int(math.sin(self.bob_phase) * BOB_AMP)

        self.photo = ImageTk.PhotoImage(display)
        cx = self.x + SPRITE_W // 2 + (new_w - SPRITE_W) // 2
        cy = self.y + SPRITE_H // 2 + bob_y + (new_h - SPRITE_H) // 2
        self.canvas.coords(self.img_id, cx, cy)
        self.canvas.itemconfig(self.img_id, image=self.photo)


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
        self._hook_running = True
        self.tray = None
        self.hwnd = None  # 主窗口句柄，用于 SetWindowRgn
        # 鼠标钩子内用于跟踪是否吞掉右键事件（仅由钩子线程读写，避免竞态）
        self._r_block = False

        self._setup_window()
        self._create_canvas()
        self._bind_canvas_events()  # canvas 事件绑定（替代钩子处理左键拖动）
        self._load_pets()
        self._setup_tray_icon()   # 原生 win32 托盘图标

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind('<Escape>', lambda e: self._on_close())

        # 全局鼠标钩子
        self._hook_proc_cb = HOOKPROC(self._hook_proc_impl)
        self._hook_thread = threading.Thread(target=self._hook_thread, daemon=True)
        self._hook_thread.start()

        self._animate()

    def _setup_window(self):
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', '#f0f0f0')
        self.root.geometry(f'{self.screen_w}x{self.screen_h}+0+0')
        self.root.config(bg='#f0f0f0')
        self.root.title(self.WINDOW_TITLE)

        self.root.update_idletasks()
        hwnd = win32gui.FindWindow(None, self.WINDOW_TITLE)
        self.hwnd = hwnd
        if hwnd:
            try:
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                # 不加 WS_EX_TRANSPARENT：之前用 WH_MOUSE_LL 钩子吞掉 LBUTTONDOWN 会让 Windows
                # 进入"按键未释放"状态，导致下一次点击不再产生事件（卡死）。
                # 现在改用 SetWindowRgn 把窗口限制为宠物矩形 —— 区域外点击直接穿透到桌面，
                # 区域内由 canvas 事件处理拖动。
                ex |= win32con.WS_EX_LAYERED | win32con.WS_EX_TOOLWINDOW
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
            except Exception as e:
                print(f"Warning: style: {e}")
        # 初始 region：根据可见宠物集合随时更新
        self._update_window_region()

    def _update_window_region(self):
        """把窗口的可点击区域限制为可见宠物矩形的并集。
        区域之外的鼠标事件直接穿透到桌面 —— 这是替代 WS_EX_TRANSPARENT 的"局部可点"方案，
        与钩子吞事件不同，它会让 Windows 正确收到鼠标释放消息，避免卡死。
        SetWindowRgn 接管传入 region 的所有权，下次调用或销毁窗口时会自动释放。
        拖动期间由 _set_window_region_fullscreen 接管，本方法不会再被调用。
        """
        if not self.hwnd or self.drag:
            return
        try:
            combined = win32gui.CreateRectRgn(0, 0, 0, 0)  # 空的初始 region
            for pet in self.pets:
                if not pet.visible:
                    continue
                x1 = max(0, pet.x)
                y1 = max(0, pet.y)
                x2 = min(self.screen_w, pet.x + SPRITE_W)
                y2 = min(self.screen_h, pet.y + SPRITE_H)
                if x2 <= x1 or y2 <= y1:
                    continue
                r = win32gui.CreateRectRgn(x1, y1, x2, y2)
                # CombineRgn(目标, src1, src2, 操作) 把 r 合入 combined；RGN_OR=2
                win32gui.CombineRgn(combined, combined, r, getattr(win32api, 'RGN_OR', 2))
            win32gui.SetWindowRgn(self.hwnd, combined, True)
        except Exception:
            # 失败回退到全屏 region（不损失功能，但点击可能落到桌面图标）
            self._set_window_region_fullscreen()

    def _set_window_region_fullscreen(self):
        """拖动期间调用：把 region 临时设为全屏，保证鼠标在屏幕任意位置
        移动都能触发 canvas 的 <B1-Motion>。"""
        if not self.hwnd:
            return
        try:
            full = win32gui.CreateRectRgn(0, 0, self.screen_w, self.screen_h)
            win32gui.SetWindowRgn(self.hwnd, full, True)
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

    def _on_canvas_btn1_press(self, event):
        pet = self._pet_at(event.x_root, event.y_root)
        if not pet:
            return
        self.drag = {'pet': pet, 'ox': event.x_root - pet.x, 'oy': event.y_root - pet.y}
        pet.dragging = True
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
        if self.drag:
            self.drag['pet'].dragging = False
            self.drag = None
        try:
            self.canvas.grab_release()
        except Exception:
            pass
        # 拖动结束，恢复成"只覆盖宠物矩形"的 region（外面点击重新穿透到桌面）
        self._update_window_region()

    def _on_canvas_btn3_press(self, event):
        pet = self._pet_at(event.x_root, event.y_root)
        if pet:
            pet.next_pose()
        return 'break'  # 阻止 canvas 把事件传到别处（在我们的 SetWindowRgn 方案里这层通常不会触发）



    def _create_canvas(self):
        self.canvas = tk.Canvas(self.root, width=self.screen_w, height=self.screen_h,
                                bg='#f0f0f0', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def _load_pets(self):
        self.pets = []
        res_dir = get_res_dir()

        if not os.path.isdir(res_dir):
            print(f"[Pet] 未找到 res 资源目录: {res_dir}")
            print("[Pet] 请在程序运行文件夹下创建 res 目录，并在其中为每个"
                  "人物建立一个子文件夹（文件夹名即人物 id），子文件夹内存放该人物的所有动作姿态图片。")
            return

        # res 下每个子文件夹即一个人物，文件夹名即人物 id
        char_ids = sorted(
            d for d in os.listdir(res_dir)
            if os.path.isdir(os.path.join(res_dir, d))
        )
        if not char_ids:
            print(f"[Pet] res 目录下没有找到任何人物文件夹: {res_dir}")
            return

        for cid in char_ids:
            char_dir = os.path.join(res_dir, cid)
            try:
                pet = MatePaw(self.canvas, char_dir, cid, cid, self.screen_w, self.screen_h)
                self.pets.append(pet)
                print(f"[Pet] 已加载人物 {cid}（共 {pet.pose_count} 个姿态）")
            except Exception as e:
                print(f"[Pet] 跳过人物 {cid}: {e}")

    # ---- 原生系统托盘图标 ----
    def _setup_tray_icon(self):
        """创建原生 win32 系统托盘图标，菜单含每人显隐开关 + 退出。"""
        try:
            self.tray = NativeTrayIcon(
                pets=self.pets,
                on_quit_callback=lambda: self.root.after(0, self._on_close),
                on_toggle_callback=self._on_tray_toggle,
            )
            self.tray.start()
        except Exception as e:
            print(f"[Tray] ERROR starting native tray: {e}")

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

    # ---- 鼠标钩子 ----
    def _hook_thread(self):
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._hook_proc_cb, None, 0)
        msg = wintypes.MSG()
        while self._hook_running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

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

    def _animate(self):
        try:
            while not self.mouse_q.empty():
                et, x, y = self.mouse_q.get_nowait()
                self._handle_mouse(et, x, y)
        except Exception:
            pass
        for pet in self.pets:
            pet.update()
        # 让窗口 region 跟随可见宠物的位置一起移动（拖动中由 fullscreen 接管，会跳过）
        self._update_window_region()
        self.root.after(UPDATE_MS, self._animate)

    def _on_close(self):
        self._hook_running = False
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
            user32.PostQuitMessage(0)
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        print(f"[mate_paw] {len(self.pets)} pets on {self.screen_w}x{self.screen_h}")
        print("左键拖动 / 右键换姿态 / 托盘图标开关人物 / Esc 退出")
        self.root.mainloop()


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
    MatePawApp().run()
