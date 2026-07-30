"""C. 行为丰富度与动画 —— 命名姿态组 / 状态机 / 瞬时反应 / 纯决策函数。

这些用例不依赖真实桌面渲染：纯函数直接用；涉及 MatePaw 的部分用临时 Tk 根 +
Canvas 构造（本环境 Tk 可无显示创建），资源图用 PIL 现画纯色 PNG。
"""
import os
import sys
import time

import pytest
from PIL import Image

import desktop_pet as dp


# ---------------------------------------------------------------------------
# 纯函数（不依赖 Tk）
# ---------------------------------------------------------------------------
def test_choose_crawl_action_first_threshold():
    # r=0 命中第一个动作 pause
    assert dp.choose_crawl_action(0.0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1) == 'pause'


def test_choose_crawl_action_none_when_below_all():
    # r 大于所有累计阈值 -> 继续爬行（None）
    assert dp.choose_crawl_action(0.999, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1) is None


def test_choose_crawl_action_middle_bucket():
    # 只开到 sleep（含）的桶，sleep 累计阈值 = 0.5；r=0.45 落在 sleep 桶
    r = 0.45
    # pause .1, look .2, turn .3, idle .4, sleep .5 -> 0.4 <= 0.45 < 0.5
    assert dp.choose_crawl_action(r, 0.1, 0.1, 0.1, 0.1, 0.1, 0.0, 0.0) == 'sleep'


def test_facing_toward():
    assert dp.facing_toward(100, 200) is True   # 目标在右 -> 朝右
    assert dp.facing_toward(100, 50) is False   # 目标在左 -> 朝左
    assert dp.facing_toward(100, 100) is True   # 同点 -> 朝右（>=）


# ---------------------------------------------------------------------------
# 命名姿态组加载（需要 Tk，构造 MatePaw）
# ---------------------------------------------------------------------------
def _make_png(path, color=(255, 0, 0, 255)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new('RGBA', (40, 60), color).save(path)


# tkinter 一个进程只允许一个 Tk 根，用 session 级 fixture 共享，避免多次 Tk() 损坏 Tcl。
@pytest.fixture(scope='session')
def tk_root():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # 不显示窗口
    yield root
    try:
        root.destroy()
    except Exception:
        pass


@pytest.fixture
def tk_canvas(tk_root):
    import tkinter as tk
    cv = tk.Canvas(tk_root, width=800, height=600)
    cv.pack()
    yield cv
    try:
        cv.destroy()
    except Exception:
        pass


@pytest.fixture
def char_dir(tmp_path):
    d = tmp_path / 'stickman'
    # 顶层文件 -> 组 a / b（向后兼容旧资源：每张顶层图一个组）
    _make_png(os.path.join(d, 'a.png'))
    _make_png(os.path.join(d, 'b.png'))
    # 命名子目录 -> 多帧组 walk（两帧）
    _make_png(os.path.join(d, 'walk', 'f1.png'))
    _make_png(os.path.join(d, 'walk', 'f2.png'))
    # 单帧命名组 idle / happy（用于瞬时反应覆盖测试）
    _make_png(os.path.join(d, 'idle', 'i.png'))
    _make_png(os.path.join(d, 'happy', 'h.png'))
    return str(d)


def _new_pet(char_dir, canvas):
    return dp.MatePaw(canvas, char_dir, 'stickman', 'stickman', 800, 600)


def test_pose_groups_loaded(char_dir, tk_canvas):
    pet = _new_pet(char_dir, tk_canvas)
    # 组按文件名排序：a, b, happy, idle, walk
    assert pet.pose_order == ['a', 'b', 'happy', 'idle', 'walk']
    assert pet.pose_count == 5
    # 多帧组 walk 含 2 帧
    assert len(pet.pose_groups['walk']) == 2
    # 顶层单帧组 a 含 1 帧
    assert len(pet.pose_groups['a']) == 1


def test_set_pose_group_and_current(char_dir, tk_canvas):
    pet = _new_pet(char_dir, tk_canvas)
    pet.set_pose_group('walk')
    assert pet.pose_order[pet.pose_index] == 'walk'
    assert pet.frame_index == 0
    assert pet.current_group_name() == 'walk'
    # 不存在的组 no-op
    before = pet.pose_index
    pet.set_pose_group('does_not_exist')
    assert pet.pose_index == before


def test_state_enters_mapped_pose_group(char_dir, tk_canvas):
    pet = _new_pet(char_dir, tk_canvas)
    pet._enter_state('looking', dp.LOOK_DURATION)
    assert pet.state == 'looking'
    # looking -> 'look' 组；资源里没有 look 组 -> 应保持当前（不崩溃）
    assert pet.current_group_name() in pet.pose_groups
    # 切到 idle 状态 -> 映射到 idle 组（资源存在）
    pet._enter_state('idle', dp.IDLE_DURATION)
    assert pet.current_group_name() == 'idle'


def test_react_transient_overrides_then_expires(char_dir, tk_canvas, monkeypatch):
    pet = _new_pet(char_dir, tk_canvas)
    pet.set_pose_group('walk')
    # 触发 happy 瞬时表情（资源有 happy 组）
    pet.react('happy')
    assert pet.current_group_name() == 'happy'  # 瞬时优先
    # 时间推进超过持续时间 -> 回到行为组 walk
    real_now = time.time()
    monkeypatch.setattr(time, 'time', lambda: real_now + 5.0)
    assert pet.current_group_name() == 'walk'


def test_react_unknown_group_falls_back(char_dir, tk_canvas, monkeypatch):
    pet = _new_pet(char_dir, tk_canvas)
    pet.set_pose_group('walk')
    pet.react('shock')  # 资源无 shock 组 -> 退化为保持当前组
    assert pet.current_group_name() == 'walk'


def test_update_runs_without_error(char_dir, tk_canvas, monkeypatch):
    pet = _new_pet(char_dir, tk_canvas)
    # 固定随机值让爬行中不发生状态切换，只移动 + 渲染，验证 update 不抛异常
    monkeypatch.setattr(dp.random, 'random', lambda: 0.999)
    # 多调几帧，覆盖 _advance_frame / _render / _move / _hits_window 路径
    for _ in range(5):
        pet.update(paused=False)
    assert pet.state == 'crawling'


# ---------------------------------------------------------------------------
# D. 交互与体验 —— 纯函数 + 空闲气泡
# ---------------------------------------------------------------------------
def test_is_tap_small_move_short_time():
    assert dp.is_tap(2, 1, 100) is True


def test_is_tap_large_move():
    assert dp.is_tap(50, 0, 100) is False


def test_is_tap_long_time():
    assert dp.is_tap(2, 1, 1000) is False


def test_pick_phrase_empty():
    assert dp.pick_phrase([]) == ""


def test_pick_phrase_from_list():
    phrases = ["a", "b", "c"]
    assert dp.pick_phrase(phrases, rng=lambda p: p[1]) == "b"


def test_idle_bubble_appears(char_dir, tk_canvas, monkeypatch):
    pet = _new_pet(char_dir, tk_canvas)
    # 强制空闲气泡必触发一次
    monkeypatch.setattr(dp, 'IDLE_BUBBLE_CHANCE', 1.0)
    monkeypatch.setattr(dp.random, 'random', lambda: 0.0)
    pet.update(paused=False)
    # 应当弹出一个气泡（bubble_until 在未来）
    assert pet.bubble_until > time.time() - 1.0


def test_react_called_on_shock_has_group(char_dir, tk_canvas):
    pet = _new_pet(char_dir, tk_canvas)
    pet.react('happy')  # happy 组在测试资源中存在
    assert pet.current_group_name() == 'happy'


# ---------------------------------------------------------------------------
# 托盘菜单（D）：新增「显示全部 / 隐藏全部 / 戳一下」且回调可触发
# ---------------------------------------------------------------------------
class _FakePet:
    def __init__(self, label, visible=True):
        self.label = label
        self.visible = visible


def test_tray_menu_has_new_actions_and_callbacks():
    calls = []
    tray = dp.PystrayTrayIcon(
        pets=[_FakePet('a'), _FakePet('b')],
        on_quit_callback=lambda: calls.append('quit'),
        on_show_all_callback=lambda: calls.append('show_all'),
        on_hide_all_callback=lambda: calls.append('hide_all'),
        on_poke_callback=lambda: calls.append('poke'),
        get_paused_callback=lambda: False,
    )
    menu = tray._build_menu()
    labels = [item.text for item in menu.items if isinstance(item.text, str)]
    assert '显示全部' in labels
    assert '隐藏全部' in labels
    assert '戳一下' in labels
    # 触发新动作回调（模拟菜单点击）
    tray._on_show_all()
    tray._on_hide_all()
    tray._on_poke()
    assert calls == ['show_all', 'hide_all', 'poke']
