# mate-paw · 桌面宠物

一个 Windows 桌面宠物程序：多只“人形猴子”在桌面自由爬行、随机暂停 / 张望，能感知窗口边缘作为障碍物，支持鼠标拖动与右键切换姿态，并在系统托盘中提供每个人物的显隐开关。

## 功能特性

- 多只宠物同时在桌面活动，自动避开其他窗口
- 左键拖动人物到任意位置
- 右键点击人物循环切换动作姿态（爬行 / 坐姿 / 招手 …）
- 系统托盘图标：每人独立显隐开关 + 暂停 / 恢复全部 + 设置 + 退出
- `ESC` 退出程序
- **资源外置**：人物图片放在 `res/` 目录，无需重新打包即可增删角色
- **配置外置**：`config.json` 覆盖默认行为（速度 / 概率 / 日志等级等），托盘“设置…”可实时调参并落盘
- **状态持久化**：位置 / 显隐 / 姿态写入 `state.json`，下次启动恢复

## 目录结构

```
（仓库根）
├── src/
│   ├── desktop_pet.py       # 主程序（入口）
│   ├── config.py            # 配置系统：默认值 + config.json 覆盖 + 版本号
│   ├── res_validator.py     # 资源目录校验（仅依赖 PIL，--check 与流水线复用）
│   └── platform_win.py      # Windows 平台封装（窗口样式 / 局部点击区域 / 鼠标钩子），
│                             #   非 Windows 自动降级为空实现，保证可 Import / 可测试
├── res/                     # 运行时人物资源（已提交），每个子文件夹 = 一个人物
│   └── stickman/
│       ├── pose1.png        # 第一个文件为默认(爬行)姿态
│       └── ...
├── pose_pipeline/           # 一键生成角色姿势流水线（脚本 + 提示词模板）
├── tests/                   # pytest 单元测试（chroma_key / 资源校验 / 配置 / 平台封装）
├── mate_paw.spec            # PyInstaller 打包配置（内嵌 res/ 与 config.default.json）
├── build.py                 # 便捷构建脚本：python build.py -> dist/mate_paw.exe
├── config.default.json      # 默认配置（与 src/config.py 的 DEFAULTS 一致，随 exe 内嵌）
├── installer/
│   └── mate_paw.nsi         # NSIS 安装器模板（每用户安装到 %LOCALAPPDATA%\mate-paw）
├── requirements.txt         # 运行 / 打包依赖
├── requirements-dev.txt     # 开发 / 测试依赖（pytest）
└── LICENSE
```

## 环境要求

- Windows（运行时；窗口 / 区域 / 鼠标钩子均依赖 Win32 API）
- Python 3.10+（开发 / 打包用）
- `tkinter`（Windows 版 Python 自带，无需额外安装）

> 说明：主程序把 Win32 相关逻辑收口在 `src/platform_win.py`。导入 `desktop_pet` 时即使不在 Windows 上也不会崩溃（相关函数为空实现），便于跨平台做单元测试；但完整功能（局部点击穿透、右键屏蔽）仅在 Windows 生效。

## 开发模式运行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/desktop_pet.py
```

程序启动后会在以下位置按序查找 `res/`（第一个存在的即生效）：脚本目录 → 项目根 → 当前工作目录；打包后的 exe 若上述位置都没有 `res`，会回退到内嵌的默认资源。

### 自检与版本

```bash
python src/desktop_pet.py --check     # 无界面自检：资源 / 字体 / 依赖
python src/desktop_pet.py --version   # 打印版本号
```

## 配置

所有可调参数见 `src/config.py` 的 `DEFAULTS`（键名与旧常量一一对应）。优先级：**DEFAULTS → 找到的 `config.json`**。

- 运行时把 `config.json` 放到 exe 同级目录或当前工作目录即可覆盖默认值；
- 托盘菜单「设置…」可实时调节速度 / 概率 / 气泡时长 / 日志等级，并写入 `config.json`；
- `config.default.json` 是默认配置副本，随 exe 内嵌作为回退，也可作为编写 `config.json` 的参考。

## 打包为 exe

```bash
pip install -r requirements.txt
python build.py                 # 等价于 pyinstaller --noconfirm mate_paw.spec
```

- 产物为单文件 `dist/mate_paw.exe`，已**内嵌默认 `res/` 与 `config.default.json`**；
- 因此分发时**无需**把 `res/` 放在 exe 同级——缺失外部 `res` 时自动回退到内嵌资源，开箱即用；若想自定义人物，再放一份 `res/` 在 exe 同级即可覆盖。
- 安装器：用 [NSIS](https://nsis.sourceforge.io/) 打开 `installer/mate_paw.nsi` 编译，生成每用户安装包（开始菜单 + 桌面快捷方式 + 卸载程序）。

## 测试

```bash
pip install -r requirements-dev.txt
pytest tests                    # 纯函数单测：色键保白、资源校验、配置合并、平台封装
```

## 如何新增 / 替换人物

1. 在 `res/` 下新建一个文件夹，文件夹名即人物 id（如 `hero`）；
2. 把该人物的所有动作姿态图片放进去（支持 `png/jpg/jpeg/bmp/gif/webp/tif/tiff`；子文件夹或 `frame_*.png` 视为多帧动画）；
3. 图片按文件名排序，**第一张作为默认姿态**，其余通过右键循环切换；
4. 直接运行即可，无需重新打包。

## 批量生成角色姿势（pose_pipeline）

`pose_pipeline/` 把「一张多人合照 → 图中每个人各 3 张姿势精灵图（爬行 / 坐下 / 挥手）」串成一条链：自动检测并裁剪每个人，生成任务清单，出图后自动抠图、合成并归档到 `res/<id>/`。保留每个人原本的长相、发型与服装，并自然补全四肢与遮挡部分。

### 环境依赖

```bash
pip install ultralytics pillow rembg onnxruntime
```

- `ultralytics`：阶段一自动检测人物（未装时可用 `detect --n N` 三等分回退）。
- `rembg` + `onnxruntime`：阶段三 AI 抠图（白色外套也安全）。
- 资源校验：`python pose_pipeline/pose_pipeline.py validate` 复用 `res_validator` 检查 `res/` 结构。

### 使用

```bash
# ① 自动检测并裁剪图中所有人，生成任务清单
python pose_pipeline/pose_pipeline.py detect <合照.png>

# ② 由 Agent / ImageGen 读取 pose_pipeline/stage2/todo.json，逐张顺序出图，存到 stage2/
#    （ImageGen 必须顺序调用，不要并行，否则会互相覆盖并触发限流）

# ③ 一键抠图 + 合成透明画布 + 落盘
python pose_pipeline/pose_pipeline.py compose

# ④ 校验 res/ 结构
python pose_pipeline/pose_pipeline.py validate
```

生成的角色会落到 `res/<人物id>/`，程序启动后自动加载，无需重新打包。

> 提示词细节、参数与踩坑经验见 `pose_pipeline/姿势生成提示词模板.md`。

## License

[MIT](LICENSE) © 2026 mate-paw
