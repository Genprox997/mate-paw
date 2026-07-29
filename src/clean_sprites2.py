"""温和背景清除：只处理真正的纯白/近白背景像素，不伤及人物内容"""
from PIL import Image
import os

FINAL = 'assets/sprites/final'


def gentle_clean(path):
    """只移除亮度极高的纯白/灰白背景（brightness>248），保留所有人物内容"""
    im = Image.open(path).convert('RGBA')
    w, h = im.size
    data = im.load()

    for y in range(h):
        for x in range(w):
            r, g, b, a = data[x, y]
            # 只处理真正接近纯白的像素（亮度>248）
            # 这种亮度只有纯白背景能达到，不会误伤皮肤/衣服
            if int(r) > 248 and int(g) > 248 and int(b) > 248:
                data[x, y] = (r, g, b, 0)

    return im


for fname in sorted(os.listdir(FINAL)):
    if not fname.endswith('.png'):
        continue
    fpath = os.path.join(FINAL, fname)
    result = gentle_clean(fpath)
    result.save(fpath)
    trans = sum(1 for x in range(result.width) for y in range(result.height)
                if result.getpixel((x, y))[3] < 128)
    total = result.width * result.height
    print(f'{fname}: {trans}/{total} transparent ({100 * trans / total:.1f}%)')

print('Gentle clean done')
