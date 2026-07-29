"""
桌面宠物应用 - Monkey Pets (v5)
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
    our_title = 'MonkeyPets_DesktopPet'
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
    fd, path = tempfile.mktemp(suffix='.ico')
    try:
        img.save(path, format='ICO', sizes=[(size, size)])
        hicon = win32gui.LoadImage(
            0, path, win32con.IMAGE_ICON, size, size,
            win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        )
        return hicon
    except Exception:
        return None


# ============================================================
# 原生 Win32 系统托盘图标（替代 pystray）
# ============================================================
class NativeTrayIcon:
    """使用纯 win32gui/win32api 实现的系统托盘图标，在冻结 exe 中稳定工作。"""

    WM_TRAY_CALLBACK = win32con.WM_USER + 1
    ID_TRAY_APP = 1000
    IDM_FIRST_TOGGLE = 2000
    IDM_QUIT = 2999

    def __init__(self, pets, on_quit_callback):
        """
        pets: list of MonkeyPet 对象（需要有 .label 和 .visible 属性）
        on_quit_callback: 退出回调函数
        """
        self.pets = pets
        self.on_quit = on_quit_callback
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
            wc.lpszClassName = "MonkeyPetsTrayWnd"
            wc.lpfnWndProc = self._wnd_proc
            wc.hInstance = win32api.GetModuleHandle(None)

            class_atom = win32gui.RegisterClass(wc)

            # 2. 创建隐藏窗口
            self.hwnd = win32gui.CreateWindowEx(
                0, class_atom, "MonkeyPets Tray",
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
                with self._lock:
                    if 0 <= idx < len(self.pets):
                        pet = self.pets[idx]
                        pet.set_visible(not pet.visible)
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
            pos = win32api.GetCursorPos()
            win32gui.SetForegroundWindow(self.hwnd)
            win32gui.TrackPopupMenu(
                menu,
                win32con.TPM_RIGHTBUTTON | win32con.TPM_RETURNCMD,
                pos[0], pos[1],
                0, self.hwnd, None
            )
            win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
            win32gui.DestroyMenu(menu)

        except Exception as e:
            print(f"[Tray] Menu error: {e}")


# ============================================================
# 宠物类
# ============================================================
class MonkeyPet:
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
class DesktopPetApp:
    WINDOW_TITLE = 'MonkeyPets_DesktopPet'

    def __init__(self):
        self.root = tk.Tk()
        self.screen_w, self.screen_h = get_screen_size()
        self.mouse_q = queue.Queue()
        self.drag = None
        self._hook = None
        self._hook_running = True
        self.tray = None

        self._setup_window()
        self._create_canvas()
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
        if hwnd:
            try:
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                ex |= win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOOLWINDOW
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
            except Exception as e:
                print(f"Warning: style: {e}")

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
                pet = MonkeyPet(self.canvas, char_dir, cid, cid, self.screen_w, self.screen_h)
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
            )
            self.tray.start()
        except Exception as e:
            print(f"[Tray] ERROR starting native tray: {e}")

    # ---- 鼠标钩子 ----
    def _hook_thread(self):
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._hook_proc_cb, None, 0)
        msg = wintypes.MSG()
        while self._hook_running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _hook_proc_impl(self, nCode, wParam, lParam):
        if nCode >= 0:
            hs = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            x, y = hs.pt.x, hs.pt.y
            if wParam == WM_LBUTTONDOWN:
                self.mouse_q.put(('down', x, y))
            elif wParam == WM_LBUTTONUP:
                self.mouse_q.put(('up', x, y))
            elif wParam == WM_RBUTTONDOWN:
                self.mouse_q.put(('rdown', x, y))
            elif wParam == WM_MOUSEMOVE and self.drag is not None:
                self.mouse_q.put(('move', x, y))
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
        if et == 'down':
            pet = self._pet_at(x, y)
            if pet:
                self.drag = {'pet': pet, 'ox': x - pet.x, 'oy': y - pet.y}
                pet.dragging = True
        elif et == 'move':
            if self.drag:
                pet = self.drag['pet']
                pet.x = min(max(x - self.drag['ox'], 0), self.screen_w - SPRITE_W)
                pet.y = min(max(y - self.drag['oy'], 0), self.screen_h - SPRITE_H)
        elif et == 'up':
            if self.drag:
                self.drag['pet'].dragging = False
                self.drag = None
        elif et == 'rdown':
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
        print(f"[MonkeyPets] {len(self.pets)} pets on {self.screen_w}x{self.screen_h}")
        print("左键拖动 / 右键换姿态 / 托盘图标开关人物 / Esc 退出")
        self.root.mainloop()


if __name__ == '__main__':
    DesktopPetApp().run()
