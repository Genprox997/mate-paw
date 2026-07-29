import sys
from PIL import Image

PET = r"D:\code\pet"
SRC1 = rf"{PET}\res\1.jpg"
SRC2 = rf"{PET}\res\2.jpg"
OUT = rf"{PET}\assets\crops"
import os
os.makedirs(OUT, exist_ok=True)

def thirds_crop(path, names, extra=0.06):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    print(f"{path}: {w}x{h}")
    n = len(names)
    seg = w / n
    for i, name in enumerate(names):
        x0 = max(0, int(seg * i - seg * extra))
        x1 = min(w, int(seg * (i + 1) + seg * extra))
        crop = im.crop((x0, 0, x1, h))
        # 适当裁剪上下留白（保留全身）
        crop.save(rf"{OUT}\{name}.jpg")
        print(f"  saved {name}.jpg  crop_x=({x0},{x1})")
    return w, h

if __name__ == "__main__":
    thirds_crop(SRC1, ["p1_green", "p2_yellow", "p3_red"])
    thirds_crop(SRC2, ["_tmp", "_tmp2", "p4_blue"])
    print("done")
