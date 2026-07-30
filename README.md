# mate-paw · 桌面宠物

一个 Windows 桌面宠物程序：多只“人形猴子”在桌面自由爬行、随机暂停 / 张望，能感知窗口边缘作为障碍物，支持鼠标拖动与右键切换姿态，并在系统托盘中提供每个人物的显隐开关。

## 功能特性

- 多只宠物同时在桌面活动，自动避开其他窗口
- **丰富的行为状态**（见下）：爬行 / 暂停发呆 / 张望 / 空闲小动作（睡觉 / 招手 / 眨眼）/ 受惊 / 开心，由随机状态机驱动
- **命名姿态组**：每个行为对应一组动画帧（缺失时自动回退），让不同行为视觉上真正不同
- 左键**拖动**人物到任意位置；轻点（短按 + 位移小）则触发**抚摸反应**（开心 + 气泡）
- 右键点击人物循环切换动作姿态（爬行 / 坐姿 / 招手 …）
- 双击人物喊「爸！」
- 空闲时随机冒气泡（语料可配），开启「跟随光标」后空闲张望会看向鼠标
- 系统托盘图标：每人独立显隐开关 + 显示全部 / 隐藏全部 + 戳一下 + 暂停 / 恢复全部 + 设置 + 关于 + 退出
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
- 托盘菜单「设置…」可实时调节速度 / 各类行为概率（暂停·张望·空闲·睡觉·招手·眨眼·空闲气泡）/ 气泡时长 / 跟随光标 / 点击抚摸 / 日志等级，并写入 `config.json`；
- `config.default.json` 是默认配置副本，随 exe 内嵌作为回退，也可作为编写 `config.json` 的参考。

### 主要行为参数（节选）

| 键 | 含义 | 默认 |
|---|---|---|
| `crawl_speed_min/max` | 爬行速度范围 | 1.5 / 3.5 |
| `pause_chance` / `look_chance` | 爬行中随机暂停 / 张望的概率 | 0.006 / 0.004 |
| `idle_chance` | 非爬行时切入空闲小动作（睡觉/招手/眨眼）的概率 | 0.0008 |
| `sleep_chance` / `wave_chance` / `blink_chance` | 空闲动作各自的概率 | 0.0004 / 0.0004 / 0.0015 |
| `idle_bubble_chance` | 空闲随机冒气泡的概率 | 0.0006 |
| `follow_cursor` | 空闲张望时看向光标 | false |
| `tap_react` | 轻点抚摸反应 | true |
| `poke_bubble` | 「戳一下」气泡文案 | 喂！ |
| `bubble_lines` | 空闲 / 抚摸气泡语料 | 见默认值 |
| `*_duration` | 各行为持续帧数区间 `[min, max]` | 见默认值 |

## 性能与渲染优化（A）

桌面宠物常驻前台、按帧驱动，渲染效率直接影响 CPU 占用与风扇。本程序在以下方面做了优化：

- **渲染缓存（`SpriteCache`）**：每只宠物按其「姿态组 + 帧序号 + 朝向」惰性缓存「已翻转的 PIL」与 `ImageTk.PhotoImage`（LRU 上限见 `photo_cache_max`）。旧实现每帧都做「翻转拷贝 + LANCZOS 缩放 + 新建 Tcl 图片」三件套，现在是命中即复用同一图片对象，只有姿态 / 帧动画 / 朝向真正变化时才重建。宠物移动只更新画布坐标（极便宜），因此多只宠物同屏时 CPU 占用显著下降。
- **窗口区域节流**：`SetWindowRgn`（局部点击穿透）只在「可见宠物矩形并集」真正变化时才调用，静止 / 显隐不变时跳过该 win32 系统调用。
- **指针查询按需**：仅在开启「跟随光标」时才每帧查询鼠标位置。
- **呼吸动感保留但零缩放**：上下 bob 浮动保留，但不再对图片做逐帧缩放，避免昂贵的像素重采样。

相关配置：

| 键 | 含义 | 默认 |
|---|---|---|
| `photo_cache_max` | 每只宠物缓存的 PhotoImage 数量上限（LRU 淘汰）；调小更省内存，调大减少重建 | 384 |
| `scale_range` | 预留：图片呼吸缩放幅度（当前渲染已改为仅位移浮动，该值暂不参与运行时缩放） | 0.025 |

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
pytest tests                    # 单元：色键保白、资源校验、配置合并、平台封装、行为状态机、交互判定
```

## 如何新增 / 替换人物

1. 在 `res/` 下新建一个文件夹，文件夹名即人物 id（如 `hero`）；
2. 把该人物的动作姿态图片放进去，按**命名姿态组**组织：
   - 顶层图片文件（`png/jpg/...`）= 一个个单帧姿态组，**文件名（去扩展名）即组名**；
   - 子文件夹 = 一组多帧动画（组内图片按文件名排序为帧序列），**文件夹名即组名**；
   - 约定组名：`walk`（默认/爬行）、`idle`、`look`、`sleep`、`wave`、`blink`、`shock`（受惊）、`happy`（开心）。行为状态机会按名取组；**缺某组时自动保持当前姿态**，所以只需提供 `walk` 也能正常运行。
3. 直接运行即可，无需重新打包；托盘「设置…」实时调参。

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
