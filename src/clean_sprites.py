"""高质量背景清除：去除所有精灵图的白斑/灰底残留"""
from PIL import Image
import os

FINAL = 'assets/sprites/final'


def clean_sprite(path):
    im = Image.open(path).convert('RGBA')
    w, h = im.size
    data = im.load()

    # Step 1: 高亮度低饱和度像素 → 透明（白/灰背景）
    for y in range(h):
        for x in range(w):
            r, g, b, a = data[x, y]
            brightness = (int(r) + int(g) + int(b)) / 3
            max_c = max(r, g, b)
            min_c = min(r, g, b)
            saturation = max_c - min_c
            if brightness > 200 and saturation < 55:
                data[x, y] = (r, g, b, 0)

    # Step 2: 从四角 flood fill，把透明区域边缘的杂色也清掉
    visited = set()
    stack = []
    for x in range(w):
        stack.append((x, 0))
        stack.append((x, h - 1))
    for y in range(h):
        stack.append((0, y))
        stack.append((w - 1, y))

    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in visited or cx < 0 or cx >= w or cy < 0 or cy >= h:
            continue
        visited.add((cx, cy))
        cr, cg, cb, ca = data[cx, cy]
        if ca < 30:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                    nr, ng, nb, na = data[nx, ny]
                    nbr = (int(nr) + int(ng) + int(nb)) / 3
                    if na < 180 or (nbr > 180 and na < 220):
                        stack.append((nx, ny))
                        if nbr > 170:
                            data[nx, ny] = (nr, ng, nb, 0)

    # Step 3: 残留的低不透明度近白像素二次清理
    for y in range(h):
        for x in range(w):
            r, g, b, a = data[x, y]
            if 0 < a < 100:
                brightness = (int(r) + int(g) + int(b)) / 3
                if brightness > 190:
                    data[x, y] = (r, g, b, 0)

    return im


for fname in sorted(os.listdir(FINAL)):
    if not fname.endswith('.png'):
        continue
    fpath = os.path.join(FINAL, fname)
    result = clean_sprite(fpath)
    result.save(fpath)
    trans = sum(1 for x in range(result.width) for y in range(result.height)
                if result.getpixel((x, y))[3] < 128)
    total = result.width * result.height
    print(f'{fname}: {trans}/{total} transparent ({100 * trans / total:.1f}%)')

print('Done cleaning all sprites')
