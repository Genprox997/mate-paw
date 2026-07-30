"""config 配置系统的单元测试。"""
import json
import os
import tempfile

from config import load_config, DEFAULTS, Config, APP_VERSION


def test_defaults_loaded_when_no_file():
    cfg, src = load_config(None)
    assert src == "defaults"
    assert cfg.fps == DEFAULTS["fps"]
    assert cfg.chroma_tolerance == DEFAULTS["chroma_tolerance"]
    assert src == "defaults"


def test_user_json_overrides_defaults():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"fps": 12, "sprite_w": 100}, f)
        path = f.name
    try:
        cfg, src = load_config(path)
        assert cfg.fps == 12               # 用户覆盖
        assert cfg.sprite_w == 100         # 用户覆盖
        assert cfg.chroma_tolerance == DEFAULTS["chroma_tolerance"]  # 仍取默认
        assert "defaults" not in src
    finally:
        os.remove(path)


def test_config_save_roundtrip():
    cfg = Config({"a": 1, "b": "x"})
    assert cfg.a == 1 and cfg.b == "x"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        path = f.name
    try:
        cfg.save(path)
        cfg2, _ = load_config(path)
        assert cfg2.a == 1 and cfg2.b == "x"
    finally:
        os.remove(path)


def test_apply_config_sets_globals():
    # 验证配置热更新会把值同步到 desktop_pet 的模块级常量
    from desktop_pet import apply_config, load_config as dl
    cfg, _ = dl(None)
    cfg.fps = 7
    cfg.sprite_w = 123
    apply_config(cfg)
    from desktop_pet import FPS, SPRITE_W
    assert FPS == 7
    assert SPRITE_W == 123


def test_version_constant():
    assert isinstance(APP_VERSION, str) and APP_VERSION
