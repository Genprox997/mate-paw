"""chroma_key 色键去背景的单元测试。"""
from PIL import Image

from desktop_pet import chroma_key


def test_removes_background_keeps_white_foreground():
    # 绿背景 + 中心白色方块；白衣服不应被误删
    im = Image.new("RGBA", (100, 100), (0, 255, 0, 255))
    for x in range(30, 70):
        for y in range(30, 70):
            im.putpixel((x, y), (255, 255, 255, 255))
    out = chroma_key(im, tolerance=60)
    # 背景角点被抠成透明
    assert out.getpixel((0, 0))[3] == 0
    # 白色前景保留
    assert out.getpixel((50, 50))[3] == 255
    assert out.getpixel((50, 50))[:3] == (255, 255, 255)


def test_preserves_fully_transparent_input():
    # 全透明 PNG 直接跳过，不误删（保留白衣服等前景）
    im = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    out = chroma_key(im, tolerance=40)
    assert out.getpixel((5, 5))[3] == 0


def test_rgb_input_converted_and_keyed():
    # 非 RGBA 输入会被转换；近黑背景在容差内被去掉
    im = Image.new("RGB", (10, 10), (10, 10, 10))
    out = chroma_key(im, tolerance=5)
    assert out.getpixel((0, 0))[3] == 0


def test_white_pixel_kept_on_green_bg():
    # 直接验证"白衣服不被误删"：孤立白像素在绿背景下应保留
    im = Image.new("RGBA", (50, 50), (0, 200, 0, 255))
    im.putpixel((25, 25), (255, 255, 255, 255))
    out = chroma_key(im, tolerance=50)
    assert out.getpixel((25, 25))[3] == 255
