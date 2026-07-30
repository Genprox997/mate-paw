# mate-paw · 桌面宠物

一个 Windows 桌面宠物程序：多只“人形猴子”在桌面自由爬行、随机暂停 / 张望，能感知窗口边缘作为障碍物，支持鼠标拖动与右键切换姿态，并在系统托盘中提供每个人物的显隐开关。

## 功能特性

- 多只宠物同时在桌面活动，自动避开其他窗口
- 左键拖动人物到任意位置
- 右键点击人物循环切换动作姿态（爬行 / 坐姿 / 招手 …）
- 系统托盘图标：每人独立显隐开关 + 退出
- `ESC` 退出程序
- **资源外置**：人物图片放在 `res/` 目录，无需重新打包即可增删角色

## 目录结构

```
（仓库根）
├── pose_pipeline/            # 一键生成角色姿势流水线（脚本 + 提示词模板）
│   ├── pose_pipeline.py      # detect / compose 两条命令串起全流程
│   └── 姿势生成提示词模板.md  # 提示词结构与流程说明
├── mate-paw/
│   ├── src/
│   │   └── desktop_pet.py    # 主程序
│   ├── res/                  # 运行时人物资源（需提交）
│   │   └── <人物id>/
│   │       ├── pose1.png     # 第一个文件为默认(爬行)姿态
│   │       ├── pose2.png     # 其余按文件名排序作为切换姿态
│   │       └── ...
│   ├── assets/               # 美术生成中间产物（已被 .gitignore 忽略）
│   ├── mate_paw.spec         # PyInstaller 打包配置
│   ├── requirements.txt
│   ├── .gitignore
│   └── LICENSE
```

## 环境要求

- Windows
- Python 3.10+（开发 / 打包用）
- `tkinter`（Windows 版 Python 自带，无需额外安装）

## 开发模式运行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/desktop_pet.py
```

程序启动后会在**运行目录下的 `res/`** 中按子文件夹加载人物；每个子文件夹名即人物 id。

## 打包为 exe

```bash
pip install -r requirements.txt
pyinstaller --noconfirm mate_paw.spec
```

生成的 `dist/mate_paw.exe` 为单文件。分发 / 运行前，需把 `res/` 文件夹放在 exe **同级目录**（即 `dist/mate_paw.exe` 与 `dist/res/` 在一起）。

## 如何新增 / 替换人物

1. 在 `res/` 下新建一个文件夹，文件夹名即人物 id（如 `hero`）；
2. 把该人物的所有动作姿态图片放进去（支持 `png/jpg/jpeg/bmp/gif/webp/tif/tiff`）；
3. 图片按文件名排序，**第一张作为默认姿态**，其余通过右键循环切换；
4. 直接运行即可，无需重新打包。

## 批量生成角色姿势（pose_pipeline）

`pose_pipeline/` 把「一张多人合照 → 图中每个人各 3 张姿势精灵图（爬行 / 坐下 / 挥手）」串成一条链：自动检测并裁剪每个人，生成任务清单，出图后自动抠图、合成并归档到 `mate-paw/res/<id>/`。保留每个人原本的长相、发型与服装，并自然补全四肢与遮挡部分。

### 环境依赖

```bash
pip install ultralytics pillow rembg onnxruntime
```
- `ultralytics`：阶段一自动检测人物（未装时可用 `detect --n N` 三等分回退）。
- `rembg` + `onnxruntime`：阶段三 AI 抠图（白色外套也安全）。

### 使用

```bash
# ① 自动检测并裁剪图中所有人，生成任务清单
python pose_pipeline/pose_pipeline.py detect <合照.png>

# ② 由 Agent / ImageGen 读取 pose_pipeline/stage2/todo.json，逐张顺序出图，存到 stage2/
#    （ImageGen 必须顺序调用，不要并行，否则会互相覆盖并触发限流）

# ③ 一键抠图 + 合成 768x1024 透明画布 + 落盘
python pose_pipeline/pose_pipeline.py compose
```

生成的角色会落到 `mate-paw/res/<人物id>/`（`<id>.png` 为默认爬行姿态，`<id>_sit.png` 坐下，`<id>_wave.png` 挥手），程序启动后自动加载，无需重新打包。

> 提示词细节、参数与踩坑经验见 `pose_pipeline/姿势生成提示词模板.md`。

## License

[MIT](LICENSE) © 2026 mate-paw
