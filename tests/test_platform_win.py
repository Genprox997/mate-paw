"""platform_win 平台抽象的单元测试：保证可导入、接口齐全、非 Windows 安全降级。"""
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
