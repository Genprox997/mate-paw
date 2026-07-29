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
mate-paw/
├── src/
│   └── desktop_pet.py        # 主程序
├── res/                      # 运行时人物资源（需提交）
│   └── <人物id>/
│       ├── pose1.png         # 第一个文件为默认(爬行)姿态
│       ├── pose2.png         # 其余按文件名排序作为切换姿态
│       └── ...
├── assets/                   # 美术生成中间产物（已被 .gitignore 忽略）
├── mate_paw.spec             # PyInstaller 打包配置
├── requirements.txt
├── .gitignore
└── LICENSE
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

## License

[MIT](LICENSE) © 2026 mate-paw
