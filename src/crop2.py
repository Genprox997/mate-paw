from PIL import Image
import os

PET = r"D:\code\pet"
OUT = rf"{PET}\assets\crops"
os.makedirs(OUT, exist_ok=True)

# 原图尺寸 2843x1280
# 手动精调坐标：基于视觉定位每个人物中心区域
CROPS = {
    # (source_file, output_name, x0, y0, x1, y1)
    ("res/1.jpg", "p1_green",   50,   0, 1050, 1280),
    ("res/1.jpg", "p2_yellow",  880,  0, 1920, 1280),
    ("res/1.jpg", "p3_red",    1750, 0, 2800, 1280),
    ("res/2.jpg", "p4_blue",   1750, 0, 2750, 1280),
}

for src, name, *box in CROPS:
    im = Image.open(rf"{PET}\{src}").convert("RGB")
    crop = im.crop(box)
    path = rf"{OUT}\{name}.jpg"
    crop.save(path)
    print(f"{name}: {crop.size} from {src} box={box}")

print("done")
