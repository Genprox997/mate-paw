#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
桌面宠物姿势生成 · 一键流水线
================================
把「一张多人照片 → 图中每个人各 3 张姿势精灵图（爬行/坐下/挥手）」的所有
手动环节串成一条链：

    python pose_pipeline.py detect  <多人照片> [--n N] [--json persons.json]
    python pose_pipeline.py compose
    （中间由 Agent / ImageGen 对 ./stage2/todo.json 逐张出图）

设计目标：去掉全部手工作业
  - 不再手动三等分裁图  → 用 YOLOv8 自动检测并裁剪每个人
  - 不再手动写外观描述  → 以「单人裁剪图」作为图生图参考，靠 input_fidelity 保身份
  - 不再手动 rembg      → compose 自动 AI 抠图 + 合成 768x1024 透明画布
  - 不再手动归档        → 自动落盘到 mate-paw/res/<id>/

三个姿势模板与「姿势生成提示词模板.md §5」保持一致。
"""

import argparse
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE1 = os.path.join(HERE, "stage1")             # 单人裁剪图 + manifest
STAGE2 = os.path.join(HERE, "stage2")             # ImageGen 生成原图（待抠图）
RES = os.path.join(HERE, "..", "res")            # 最终落盘（桌面宠物资源目录，与运行时一致）

# 复用桌面宠物的资源校验（共享逻辑，避免重复实现）
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from res_validator import validate_res  # noqa: E402

POSES = [("", "crawl"), ("_sit", "sit"), ("_wave", "wave")]

# ---------------------------------------------------------------------------
# 姿势模板（身份段用 <外观描述> 占位；图生图保真足够时可留空，自动替换为
# "the person shown in the reference photo"）
# ---------------------------------------------------------------------------
POSE_PROMPTS = {
    "crawl": """Photorealistic image-to-image transformation of the reference photo.
Keep the EXACT same real person from the reference: identical face, skin tone, facial features<外观描述>.
Do NOT change identity, do NOT swap with another person, do NOT convert to anime, illustration, cartoon, or 3D render. Maintain realistic photo style and natural lighting.
Transform the person into a desktop pet crawling pose: crouching on all fours, both hands and both feet touching the ground, back roughly horizontal, head up looking forward, full body visible from a slightly raised front-side angle.
Remove the original background and all surroundings. Use transparent background.
Naturally and plausibly reconstruct any occluded or missing body parts - hands, fingers, arms, legs, feet, and any clothing hidden behind objects or other people - so the full body is complete and anatomically correct for the pose.
High quality, clean edges, 768x1024 pixels.""",

    "sit": """Photorealistic image-to-image transformation of the reference photo.
Keep the EXACT same real person from the reference: identical face, skin tone, facial features<外观描述>.
Do NOT change identity, do NOT swap with another person, do NOT convert to anime, illustration, cartoon, or 3D render. Maintain realistic photo style and natural lighting.
Transform the person into a desktop pet sitting pose: sitting on the ground, knees bent up or cross-legged, both hands resting naturally on the knees or beside the body, torso upright, looking forward, full body visible.
Remove the original background and all surroundings. Use transparent background.
Naturally and plausibly reconstruct any occluded or missing body parts - hands, fingers, arms, legs, feet, and any clothing hidden behind objects or other people - so the full body is complete and anatomically correct for the pose.
High quality, clean edges, 768x1024 pixels.""",

    "wave": """Photorealistic image-to-image transformation of the reference photo.
Keep the EXACT same real person from the reference: identical face, skin tone, facial features<外观描述>.
Do NOT change identity, do NOT swap with another person, do NOT convert to anime, illustration, cartoon, or 3D render. Maintain realistic photo style and natural lighting.
Transform the person into a desktop pet waving pose: sitting on the ground cross-legged, right hand raised high and waving hello, left hand resting naturally on the leg, friendly expression, looking forward, full body visible.
Remove the original background and all surroundings. Use transparent background.
Naturally and plausibly reconstruct any occluded or missing body parts - hands, fingers, arms, legs, feet, and any clothing hidden behind objects or other people - so the full body is complete and anatomically correct for the pose.
High quality, clean edges, 768x1024 pixels.""",
}


def build_prompt(pose, appearance):
    tmpl = POSE_PROMPTS[pose]
    appearance = appearance.strip() if appearance else ""
    # 有外观时追加 "same black hair, same red hoodie..."；无外观时直接省略，靠图生图保真
    desc = f", same {appearance}" if appearance else ""
    return tmpl.replace("<外观描述>", desc)


# ---------------------------------------------------------------------------
# 阶段一：人物检测 + 裁剪
# ---------------------------------------------------------------------------
def detect_yolo(img_path):
    """用 YOLOv8 检测所有人，返回按 x 中心排序的 [(id, (x1,y1,x2,y2)), ...]"""
    from ultralytics import YOLO
    model = YOLO("yolov8n.pt")
    res = model(img_path, classes=[0], verbose=False)[0]
    boxes = res.boxes.xyxy.cpu().numpy()
    # 过滤过小框（避免误检），按 x 中心排序
    h = res.orig_shape[0]
    good = [b for b in boxes if (b[3] - b[1]) > 0.12 * h]
    good.sort(key=lambda b: (b[0] + b[2]) / 2)
    return [(i + 1, tuple(int(v) for v in b)) for i, b in enumerate(good)]


def detect_thirds(img_path, n):
    """回退方案：按垂直等分给 N 个人"""
    im = Image.open(img_path).convert("RGB")
    w, h = im.size
    seg = w / n
    out = []
    for i in range(n):
        x0 = max(0, int(seg * i - seg * 0.06))
        x1 = min(w, int(seg * (i + 1) + seg * 0.06))
        out.append((i + 1, (x0, 0, x1, h)))
    return out


def detect_persons(img_path, n=None, json_path=None):
    if json_path and os.path.exists(json_path):
        data = json.load(open(json_path, encoding="utf-8"))
        # 支持 [{"id":1,"bbox":[...],"appearance":"..."}] 或 [[x1,y1,x2,y2], ...]
        persons = []
        for i, p in enumerate(data):
            if isinstance(p, dict):
                persons.append((p.get("id", i + 1), tuple(p["bbox"]), p.get("appearance", "")))
            else:
                persons.append((i + 1, tuple(p), ""))
        return persons
    try:
        return [(i, b, "") for i, b in detect_yolo(img_path)]
    except Exception as e:
        print(f"[warn] YOLO 不可用（{e}），回退三等分。请用 --n 指定人数，或先 pip install ultralytics。")
        if not n:
            raise SystemExit("缺少人数：请加 --n N 或 --json persons.json")
        return [(i, b, "") for i, b in detect_thirds(img_path, n)]


def cmd_detect(args):
    stage1 = args.stage1 or STAGE1
    stage2 = args.stage2 or STAGE2
    os.makedirs(stage1, exist_ok=True)
    os.makedirs(stage2, exist_ok=True)
    persons = detect_persons(args.image, n=args.n, json_path=args.json)
    im = Image.open(args.image).convert("RGB")
    manifest = []
    for pid, (x1, y1, x2, y2), appearance in persons:
        # 适度外扩，避免切到头发/脚，并裁掉顶部留白
        pad_x = int((x2 - x1) * 0.04)
        x1, x2 = max(0, x1 - pad_x), min(im.width, x2 + pad_x)
        y1, y2 = max(0, y1 - int((y2 - y1) * 0.03)), min(im.height, y2)
        crop = im.crop((x1, y1, x2, y2))
        crop_path = os.path.join(stage1, f"person_{pid}.png")
        crop.save(crop_path)
        jobs = []
        for suffix, pose in POSES:
            jobs.append({
                "out": f"person_{pid}{suffix}.png",
                "pose": pose,
                "prompt": build_prompt(pose, appearance),
            })
        manifest.append({
            "id": f"person_{pid}",
            "crop": crop_path,
            "appearance": appearance,
            "bbox": [x1, y1, x2, y2],
            "jobs": jobs,
        })
        print(f"  person_{pid}: bbox=({x1},{y1},{x2},{y2}) crop->{crop_path}")
    mpath = os.path.join(stage1, "manifest.json")
    json.dump(manifest, open(mpath, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    # 同时导出「待生成」清单，供 Agent / ImageGen 直接遍历
    todo = []
    for m in manifest:
        for j in m["jobs"]:
            todo.append({"id": m["id"], "crop": m["crop"],
                         "out": j["out"], "pose": j["pose"], "prompt": j["prompt"]})
    json.dump(todo, open(os.path.join(stage2, "todo.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n检测到 {len(persons)} 个人 → {mpath}")
    print(f"生成任务清单 → {os.path.join(stage2, 'todo.json')}（共 {len(todo)} 张）")


# ---------------------------------------------------------------------------
# Agent 步骤占位：对 ./stage2/todo.json 逐张调用 ImageGen
#   image = crop 路径, prompt = prompt, size=768x1024, background=transparent,
#   input_fidelity=high, quality=high
#   生成结果保存为 STAGE2/<out>
#
# 关键坑点（已验证）：
#   - 必须顺序调用，不要并行。ImageGen 并行会覆盖同一路径，且极易触发
#     "RequestLimitExceeded.JobNumExceed / 150 个任务上限" 的限流。
#   - 每生成一张，立即把返回文件重命名为 STAGE2/<out> 再继续下一张，避免后续
#     compose 找不到对应文件。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 阶段三：批量抠图 + 合成 768x1024 透明画布 + 落盘
# ---------------------------------------------------------------------------
def compose_one(src_path, dst_path, target=(768, 1024), pad=0.06):
    from rembg import remove
    im = Image.open(src_path).convert("RGBA")
    try:
        im = remove(im)                         # AI 抠图（白色外套也安全）
    except Exception as e:
        print(f"  [warn] rembg 抠图失败（{e}），保留原图透明通道继续")
    # 去掉完全透明的外边界
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    if not im.getbbox():
        print(f"  [skip] 完全透明，跳过: {src_path}")
        return
    iw, ih = im.size
    tw, th = target
    scale = min((tw * (1 - pad)) / iw, (th * (1 - pad)) / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", target, (0, 0, 0, 0))
    canvas.paste(im, ((tw - nw) // 2, (th - nh) // 2), im)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    canvas.save(dst_path)


def cmd_compose(args):
    stage2 = args.stage2 or STAGE2
    res = args.res or RES
    os.makedirs(res, exist_ok=True)
    todo_path = os.path.join(stage2, "todo.json")
    if not os.path.exists(todo_path):
        raise SystemExit("找不到 todo.json，请先 detect 并由 Agent 完成生成")
    todo = json.load(open(todo_path, encoding="utf-8"))
    for job in todo:
        raw = os.path.join(stage2, job["out"])
        if not os.path.exists(raw):
            print(f"  [skip] 缺生成图: {raw}")
            continue
        dst = os.path.join(res, job["id"], job["out"])
        compose_one(raw, dst)
        print(f"  composed → {dst}")
    print("\ncompose 完成，已落盘到 mate-paw/res/")


def cmd_validate(args):
    """校验 res 资源目录：图片可读性 / 透明度 / 姿态完整性。"""
    res = args.res or RES
    report = validate_res(res)
    if report["missing"]:
        print(f"[FAIL] 未找到 res 目录: {res}")
        raise SystemExit(1)
    if report["empty"]:
        print(f"[WARN] res 目录下没有任何人物文件夹: {res}")
        raise SystemExit(0)
    print(f"res 目录: {res}（{len(report['chars'])} 个人物）")
    any_fail = False
    for name, info in report["chars"].items():
        if info["ok"]:
            print(f"  [OK]   {name}")
        else:
            any_fail = True
            print(f"  [FAIL] {name}:")
            for iss in info["issues"]:
                print(f"         - {iss}")
    print("校验结果:", "通过" if not any_fail else "存在问题")
    raise SystemExit(1 if any_fail else 0)


def main():
    ap = argparse.ArgumentParser(description="桌面宠物姿势生成一键流水线")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="检测并裁剪每个人 + 生成任务清单")
    d.add_argument("image", help="多人照片路径")
    d.add_argument("--n", type=int, default=None, help="回退：人数（三等分）")
    d.add_argument("--json", default=None, help="手动 bbox/外观 JSON")
    d.add_argument("--stage1", default=None, help="单人裁剪输出目录（默认 ./stage1）")
    d.add_argument("--stage2", default=None, help="任务清单目录（默认 ./stage2）")
    d.set_defaults(func=cmd_detect)

    c = sub.add_parser("compose", help="批量抠图 + 合成 + 落盘")
    c.add_argument("--stage2", default=None, help="生成原图目录（默认 ./stage2）")
    c.add_argument("--res", default=None, help="最终落盘目录（默认 ../res）")
    c.set_defaults(func=cmd_compose)

    v = sub.add_parser("validate", help="校验 res 资源目录（可读性/透明度/姿态完整性）")
    v.add_argument("--res", default=None, help="资源目录（默认 ../res）")
    v.set_defaults(func=cmd_validate)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
