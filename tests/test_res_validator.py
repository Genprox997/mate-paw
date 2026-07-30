"""res_validator 资源校验的单元测试（仅依赖 PIL）。"""
from PIL import Image

from res_validator import validate_character, validate_res


def _make_png(path, opaque=True):
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGBA", (8, 8), (255, 0, 0, 255 if opaque else 0))
    img.save(path)


def test_validate_character_valid(tmp_path):
    d = tmp_path / "hero"
    _make_png(str(d / "pose1.png"))
    ok, issues = validate_character(str(d))
    assert ok is True
    assert issues == []


def test_validate_character_empty(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    ok, issues = validate_character(str(d))
    assert ok is False
    assert any("没有任何图片" in i for i in issues)


def test_validate_res_missing():
    res = validate_res("/nonexistent/path/xyz")
    assert res["missing"] is True
    assert res["ok"] is False


def test_validate_res_empty(tmp_path):
    res = validate_res(str(tmp_path))
    assert res["empty"] is True
    assert res["ok"] is False


def test_validate_res_valid(tmp_path):
    d = tmp_path / "hero"
    _make_png(str(d / "p1.png"))
    res = validate_res(str(tmp_path))
    assert res["ok"] is True
    assert "hero" in res["chars"]
    assert res["chars"]["hero"]["ok"] is True
