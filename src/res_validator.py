"""
资源目录校验（仅依赖 PIL + os）
================================
供两处复用：
  - 桌面宠物的 `--check` 自检（src/desktop_pet.py）
  - 姿势生成流水线的 `validate` 子命令（pose_pipeline/pose_pipeline.py）

校验内容：
  - res 目录是否存在、是否至少含一个人物文件夹
  - 每个人物目录下是否有可用图片（顶层图片 = 单帧姿态；子目录 = 多帧姿态）
  - 每张图能否打开；非透明格式给出提示（运行时走色键）；
    完全透明的图给出告警（运行时不可见）
"""

import os

from PIL import Image

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff')


def list_images(d):
    return sorted(f for f in os.listdir(d)
                  if os.path.splitext(f)[1].lower() in IMAGE_EXTS)


def validate_character(char_dir):
    """校验单个人物目录，返回 (ok, [issues])。"""
    issues = []
    entries = sorted(os.listdir(char_dir))
    img_files = [e for e in entries
                 if os.path.isfile(os.path.join(char_dir, e))
                 and os.path.splitext(e)[1].lower() in IMAGE_EXTS]
    subdirs = [e for e in entries if os.path.isdir(os.path.join(char_dir, e))]

    if not img_files and not subdirs:
        return False, ["没有任何图片或姿态子目录"]

    total_frames = 0
    for fn in img_files:
        p = os.path.join(char_dir, fn)
        try:
            im = Image.open(p)
            im.load()
        except Exception as e:
            issues.append(f"{fn}: 无法打开 ({e})")
            continue
        total_frames += 1
        if im.mode != 'RGBA':
            issues.append(f"{fn}: 非透明格式({im.mode})，将按色键去背景")
        else:
            try:
                alpha = im.split()[3]
                # 最大 alpha == 0 表示整张全透明
                if alpha.getextrema()[1] == 0:
                    issues.append(f"{fn}: 完全透明，运行时不可见")
            except Exception:
                pass

    for sd in subdirs:
        frames = list_images(os.path.join(char_dir, sd))
        if not frames:
            issues.append(f"子目录 {sd}/: 没有帧图片")
        else:
            total_frames += len(frames)

    ok = (len(issues) == 0) and (total_frames > 0)
    return ok, issues


def validate_res(res_dir):
    """校验整个 res 目录。

    返回 {'ok': bool, 'missing': bool, 'empty': bool,
          'chars': {name: {'ok': bool, 'issues': [...]}}}
    """
    result = {'ok': True, 'missing': False, 'empty': False, 'chars': {}}
    if not os.path.isdir(res_dir):
        result['missing'] = True
        result['ok'] = False
        return result
    chars = [d for d in sorted(os.listdir(res_dir))
             if os.path.isdir(os.path.join(res_dir, d))]
    if not chars:
        result['empty'] = True
        result['ok'] = False
        return result
    for c in chars:
        ok, issues = validate_character(os.path.join(res_dir, c))
        result['chars'][c] = {'ok': ok, 'issues': issues}
        if not ok:
            result['ok'] = False
    return result
