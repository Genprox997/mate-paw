"""
Windows 平台相关封装（屏幕尺寸 / 窗口样式 / 局部可点击区域 / 低级鼠标钩子）。

把 desktop_pet.py 里散落的 win32/ctypes 调用集中到这里，目的有两点：
  1. 主程序不再直接 import win32gui/win32con/win32api，非 Windows 平台也能
     import desktop_pet（HAS_WIN32=False 时相关函数为空实现），便于跨平台 Import
     与单元测试；
  2. Windows 专属逻辑收口到一个文件，后续维护/排查更清晰。

非 Windows 下桌面宠物会退化为普通全屏透明窗口（无局部点击裁剪、无右键屏蔽），
只用于开发 / 测试，不会崩溃。
"""

import sys
import threading

HAS_WIN32 = sys.platform == "win32"

if HAS_WIN32:
    import win32gui
    import win32con
    import win32api
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    # 区域函数（CreateRectRgn / CombineRgn / SetWindowRgn）在部分 pywin32 版本里
    # 并未通过 win32gui 导出，这里直接用 ctypes 调 gdi32/user32，行为更稳定。
    gdi32.CreateRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    gdi32.CreateRectRgn.restype = ctypes.c_void_p
    gdi32.CombineRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    gdi32.CombineRgn.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteObject.restype = ctypes.c_int
    user32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowRgn.restype = ctypes.c_int

    # 低级鼠标钩子相关常量
    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_MOUSEMOVE = 0x0200
    WM_RBUTTONDOWN = 0x0204
    WM_RBUTTONUP = 0x0205
    RGN_OR = getattr(win32api, "RGN_OR", 2)

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", wintypes.POINT),
            ("mouseData", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
        ]

    HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
    )

    def get_screen_size():
        return win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)

    def find_pet_window(title):
        """按标题查找主窗口句柄（找不到返回 None）。"""
        return win32gui.FindWindow(None, title)

    def set_layered_tool_window(hwnd):
        """给窗口加上 WS_EX_LAYERED | WS_EX_TOOLWINDOW，避免任务栏/ Alt-Tab 出现。"""
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        ex |= win32con.WS_EX_LAYERED | win32con.WS_EX_TOOLWINDOW
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)

    def set_window_region(hwnd, rects):
        """把窗口可点击区域限制为若干矩形（窗口坐标）的并集。

        rects: list of (x1, y1, x2, y2)。SetWindowRgn 接管 region 所有权，
        下次调用或销毁窗口时由系统自动释放（故 combined 不再 DeleteObject）。

        关键：rects 为空时**绝不能**创建零尺寸 region —— 空 region 会让整个
        Toplevel 窗口变成不可见/不可交互（桌宠整体消失且无法恢复）。此时改为
        SetWindowRgn(hwnd, NULL) 移除限制，使整窗可见（透明背景区域仍透明，
        仅失去"点击穿透"，但桌宠不会消失）。
        """
        if not rects:
            # 无矩形并集：移除 region 限制（整窗可见），避免空 region 使窗口消失。
            user32.SetWindowRgn(hwnd, None, 1)
            return
        combined = gdi32.CreateRectRgn(0, 0, 0, 0)
        for (x1, y1, x2, y2) in rects:
            if x2 <= x1 or y2 <= y1:
                continue
            r = gdi32.CreateRectRgn(x1, y1, x2, y2)
            gdi32.CombineRgn(combined, combined, r, RGN_OR)
            gdi32.DeleteObject(r)  # 中间 region 合并后释放
        user32.SetWindowRgn(hwnd, combined, 1)

    def set_window_region_fullscreen(hwnd, w, h):
        """把窗口可点击区域临时设为全屏（拖动期间用，保证任意位置都能收到 canvas 事件）。"""
        full = gdi32.CreateRectRgn(0, 0, w, h)
        user32.SetWindowRgn(hwnd, full, 1)

    def enum_window_rects(screen_w, screen_h, skip_title="mate_paw"):
        """枚举桌面上的可见窗口矩形，排除任务栏/全屏/过小的窗口，返回 [(l,t,r,b), ...]。

        用于让宠物把"其他窗口"当作障碍物。
        """
        rects = []

        def cb(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd)
                if not title or title == skip_title:
                    return True
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
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

        win32gui.EnumWindows(cb, None)
        return rects

    def install_mouse_hook(callback):
        """安装低级鼠标钩子并启动消息泵线程。

        callback(nCode, wParam, lParam) -> int；返回 1 表示吞掉该事件。
        返回 (hook_handle, thread, proc)，三者需保持引用以防被 GC；
        卸载时把 hook_handle 传给 uninstall_mouse_hook。
        """
        proc = HOOKPROC(callback)
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, proc, None, 0)

        def pump():
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        t = threading.Thread(target=pump, daemon=True)
        t.start()
        return hook, t, proc

    def uninstall_mouse_hook(hook):
        """卸载钩子并发送 WM_QUIT 让消息泵线程退出。"""
        if hook:
            user32.UnhookWindowsHookEx(hook)
        user32.PostQuitMessage(0)

    user32.GetLayeredWindowAttributes.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_byte), ctypes.POINTER(ctypes.c_uint),
    ]
    user32.GetLayeredWindowAttributes.restype = ctypes.c_int
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_int

    def is_window_visible(hwnd):
        """窗口当前是否可见（被最小化/隐藏返回 False）。"""
        try:
            return bool(user32.IsWindowVisible(hwnd))
        except Exception:
            return True

    def get_window_exstyle(hwnd):
        """返回扩展样式；用于判断 WS_EX_LAYERED 是否仍生效。"""
        try:
            return win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        except Exception:
            return 0

    def get_layered_colorkey(hwnd):
        """返回分层颜色键的 COLORREF（如 0x00f0f0f0）；未分层/无颜色键/出错返回 None。

        用于检测「颜色键透明」是否被 DWM 重置：失效时返回 0 或 None。
        """
        try:
            pcr = ctypes.c_uint()
            pa = ctypes.c_byte()
            pf = ctypes.c_uint()
            if user32.GetLayeredWindowAttributes(
                hwnd, ctypes.byref(pcr), ctypes.byref(pa), ctypes.byref(pf)
            ):
                return pcr.value
        except Exception:
            pass
        return None

    def show_window(hwnd):
        """把可能被隐藏/最小化的窗口重新显示（SW_SHOW=5）。"""
        try:
            user32.ShowWindow(hwnd, 5)
        except Exception:
            pass

else:
    # -------- 非 Windows 平台：安全空实现，保证可 import / 可测试 --------
    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = WM_LBUTTONUP = WM_MOUSEMOVE = 0
    WM_RBUTTONDOWN = WM_RBUTTONUP = 0
    MSLLHOOKSTRUCT = None
    HOOKPROC = None
    RGN_OR = 2

    def get_screen_size():
        # 非 Windows 下退化分辨率，仅供开发 / 测试
        return 1920, 1080

    def find_pet_window(title):
        return None

    def set_layered_tool_window(hwnd):
        pass

    def set_window_region(hwnd, rects):
        pass

    def set_window_region_fullscreen(hwnd, w, h):
        pass

    def enum_window_rects(screen_w, screen_h, skip_title="mate_paw"):
        return []

    def install_mouse_hook(callback):
        return None, None, None

    def uninstall_mouse_hook(hook):
        pass

    def is_window_visible(hwnd):
        return True

    def get_window_exstyle(hwnd):
        return 0

    def get_layered_colorkey(hwnd):
        return None

    def show_window(hwnd):
        pass
