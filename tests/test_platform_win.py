"""platform_win 平台抽象的单元测试：保证可导入、接口齐全、非 Windows 安全降级。"""
from unittest.mock import MagicMock, patch

import platform_win


def test_has_win32_is_bool():
    assert isinstance(platform_win.HAS_WIN32, bool)


def test_functions_exist():
    for fn in (
        "get_screen_size",
        "find_pet_window",
        "set_layered_tool_window",
        "set_window_region",
        "set_window_region_fullscreen",
        "enum_window_rects",
        "install_mouse_hook",
        "uninstall_mouse_hook",
    ):
        assert callable(getattr(platform_win, fn))


def test_get_screen_size_returns_tuple():
    s = platform_win.get_screen_size()
    assert isinstance(s, tuple) and len(s) == 2
    assert all(isinstance(v, int) for v in s)
    assert s[0] > 0 and s[1] > 0


def test_enum_window_rects_returns_list():
    rects = platform_win.enum_window_rects(1920, 1080, "mate_paw")
    assert isinstance(rects, list)


def test_set_window_region_empty_uses_null_not_empty_region():
    """空 rects 必须移除 region（SetWindowRgn(hwnd, NULL)）而不是创建零尺寸 region。

    回归测试：旧实现空 rects 会 CreateRectRgn(0,0,0,0) 后 SetWindowRgn，
    空 region 令整窗不可见（桌宠整体消失且无法自行恢复）。
    """
    fake_gdi = MagicMock()
    fake_user = MagicMock()
    fake_gdi.CreateRectRgn.return_value = 123
    with patch.object(platform_win, "gdi32", fake_gdi), \
         patch.object(platform_win, "user32", fake_user):
        platform_win.set_window_region(999, [])
    # 没有矩形可合并 → 不应再创建 region
    fake_gdi.CreateRectRgn.assert_not_called()
    # 必须移除 region 限制（NULL），使整窗可见而非不可见
    fake_user.SetWindowRgn.assert_called_once_with(999, None, 1)


def test_set_window_region_nonempty_combines_rects():
    """非空 rects 正常合并并集并设为窗口 region。"""
    fake_gdi = MagicMock()
    fake_user = MagicMock()
    fake_gdi.CreateRectRgn.return_value = 123
    with patch.object(platform_win, "gdi32", fake_gdi), \
         patch.object(platform_win, "user32", fake_user):
        platform_win.set_window_region(999, [(0, 0, 10, 10), (10, 10, 20, 20)])
    # combined + 2 个矩形 = 3 次 CreateRectRgn
    assert fake_gdi.CreateRectRgn.call_count == 3
    fake_user.SetWindowRgn.assert_called_once_with(999, 123, 1)
