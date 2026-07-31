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


def test_floodfill_preserves_internal_light_regions():
    """泛洪填充核心保证：内部与背景同色的区域（如白裤子）因不连通边缘而保留。

    构造：白背景 + 人物轮廓（深色边缘包围的白色内部区域）。
    旧版全局匹配会把「白色内部」也删掉（身体空洞）；新版泛洪只删边缘连通部分。
    """
    # 100x100 白背景，中间画一个「人物」：深色外框 + 白色内部（模拟白裤子）
    im = Image.new("RGBA", (100, 100), (240, 240, 240, 255))  # 近白背景
    # 深色「人物」外框（不连通到边缘，因为被背景包围——这里简化为直接在中心画）
    # 实际上为了测试泛洪，我们需要：边缘是背景色，中间有一个被非背景色包围的同色区域
    # 画法：全白底 → 中间 30x60 的矩形区域用深色描边(2px) → 内部留白
    cx, cy, rw, rh = 35, 20, 30, 60  # 人物区域
    for x in range(cx, cx + rw):
        for y in range(cy, cy + rh):
            if (x == cx or x == cx + rw - 1 or y == cy or y == cy + rh - 1):
                im.putpixel((x, y), (80, 60, 40, 255))  # 深色边框
            else:
                im.putpixel((x, y), (250, 250, 250, 255))  # 白色内部（=白裤子）

    out = chroma_key(im, tolerance=50)
    # 边缘背景应被移除
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((99, 99))[3] == 0
    # 深色边框保留（人物轮廓）
    mid_x = cx + rw // 2
    assert out.getpixel((cx, cy + rh // 2))[3] == 255  # 左边框
    # 关键：白色内部（白裤子）必须保留！这是修复的核心
    assert out.getpixel((mid_x, cy + rh // 2))[3] == 255
    assert out.getpixel((mid_x, cy + rh // 2))[:3] == (250, 250, 250)


def test_skips_rembg_image_with_minor_edge_leakage():
    """rembg 预处理的透明图：即使边缘有 1-2 个像素不透明（脚/手触边），
    也应跳过色键，避免把深色衣物当背景删掉。

    回归测试：xjy_wave.png 底边中点有 1 个近不透明像素(alpha=254)，
    旧版(全透明才跳过)会以深色为背景色做泛洪，误删 12 万像素。
    """
    # 模拟：大部分边缘透明的图，仅底边中点有 1 个不透明像素
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))  # 全透明底
    # 放一个「人物」在中间（不透明）
    for x in range(30, 70):
        for y in range(20, 80):
            im.putpixel((x, y), (40, 30, 20, 255))  # 深色衣物
    # 底边中点有 1 个不透明像素（模拟脚触边）
    im.putpixel((50, 99), (30, 20, 10, 250))

    out = chroma_key(im, tolerance=40)
    # 应该被跳过：所有像素保持不变
    for x in range(30, 70):
        for y in range(20, 80):
            assert out.getpixel((x, y))[3] == 255, f"pixel ({x},{y}) should stay opaque"
    # 底边那个泄漏像素也不应触发处理
    assert out.getpixel((50, 99))[3] == 250
