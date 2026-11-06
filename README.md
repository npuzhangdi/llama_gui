# Llama Studio

**Version: v0.0.4** · Windows 10 / 11 · Python + PySide6 · 2026-11-06

> Documentation order: English first, Chinese below. Both parts describe the same version and the same usage.

---

# English

## 1. Overview

Llama Studio is a local GUI front-end for **llama.cpp**. It provides:

- **Chat** with a local GGUF model, either through the OpenAI-compatible HTTP API of `llama-server` (streaming bubbles + token metrics) or through a direct terminal session with `llama-cli`;
- **Service hosting**: start `llama-server` so other applications can call the API, optionally with the whole window hidden in the system tray;
- **Conversation management**: projects containing multiple conversations, temporary conversations, archive / delete / move / rename;
- **Per-conversation system prompts** and a customizable appearance (theme, accent, background, glass, font size);
- A grouped parameter centre with search, per-mode filtering and a live command-line preview.

Llama Studio does **not** bundle llama.cpp binaries or model files. You must supply `llama-server.exe` / `llama-cli.exe` and your own `.gguf` models.

## 2. Requirements

| Item | Requirement |
| --- | --- |
| Operating system | Windows 10 / 11, 64-bit |
| Python | 3.9 or newer, 64-bit CPython (WindowsApps aliases, MinGW builds and 32-bit builds are ignored) |
| Python package | `PySide6 >= 6.6, < 7` — installed automatically by `first_run.bat` |
| llama.cpp | A release folder containing `llama-server.exe` and `llama-cli.exe` |
| Model | One or more `.gguf` files |

## 3. First-time setup

1. Copy the **entire** `v0.0.4` folder to any location. Paths containing spaces are supported; no absolute path is hard-coded.
2. Double-click **`first_run.bat`**. All console output is in English and follows steps `[1]` to `[6]`:

| Step | What it does |
| --- | --- |
| `[1]` | Detects usable Python installations. **None found** → opens `https://www.python.org/downloads/` and exits. **One found** → uses it automatically. **Several found** → prints a numbered list and asks you to choose. |
| `[2]` | Creates `.venv` with the selected interpreter. An existing but broken or mismatched `.venv` (for example one copied from another computer) is rebuilt automatically. |
| `[3]` | Benchmarks 7 PyPI indexes in parallel (PyPI, Tsinghua, Aliyun, USTC, Tencent, Huawei, Douban) and ranks them by response time. |
| `[4]` | Installs `requirements.txt` from the fastest index; on failure it falls back to the next index in the ranking. |
| `[5]` | Rebuilds `LlamaGUI.exe`, `uninstall.exe`, `.venv\Scripts\LlamaRuntime.exe` and the custom application icons for the local interpreter. |
| `[6]` | `Setup complete.` — the application is ready. |

3. Double-click **`LlamaGUI.exe`** to start.

`LlamaGUI.exe` is a lightweight launcher (below 1 MB), **not** a single-file bundle. It uses the local `.venv` to run `main.py` and shows no console window. Keep it in the same folder as `main.py` and `.venv`; moving the executable alone will break it.

## 4. Launch options

| Command | Behaviour |
| --- | --- |
| `LlamaGUI.exe` | Normal start with the main window |
| `LlamaGUI.exe --tray` | Starts with no window, tray icon only |
| `LlamaGUI.exe --tray --start-server` | No window, and `llama-server` is started automatically |
| `.venv\Scripts\python.exe main.py` | Manual start, useful for debugging (opens a console) |

For the arguments, create a Windows shortcut and append them to the **Target** field, e.g. `"...\LlamaGUI.exe" --tray --start-server`.

## 5. Using the application

### 5.1 Conversation manager (left sidebar, below Chat / Service / Models)

- **＋** opens the *New Conversation* dialog: name, project (including creating a new project on the spot, or *Temporary conversation / not in a project*), and a system prompt dedicated to that conversation.
- **▣** creates a project. A project can hold any number of conversations and can be collapsed, renamed or deleted (deleting a project converts its conversations into temporary ones).
- Each row has a **⋯** menu: rename, move to project, archive / unarchive, delete. Archived conversations are listed under the *Archived* section at the bottom.
- Clicking a row switches conversations: the current messages and prompt are saved first, then the target conversation is loaded. The first user message is used as the conversation title.
- Data is stored in `data/sessions.json`; the file is written with a short debounce, so changes survive restarts.

### 5.2 Per-conversation system prompt

The *System prompt (applies to the current conversation only)* card is expanded by default on the chat page. Editing it applies immediately and is saved to that conversation. The *System prompt* button in the right of the header collapses / expands the card. Prompts are not shared between conversations.

### 5.3 Appearance (gear icon, top-right of the title bar)

The settings dialog is non-modal: every change applies instantly and is saved automatically. Available options are light / dark theme, glass effect, background opacity, UI font size, accent colour (7 presets + custom), window background, panel / card background, user bubble colour, background image, and *Restore defaults*. Text, border and highlight colours are derived automatically from the chosen background so a dark background remains readable.

### 5.4 Service workspace

- Set the llama.cpp folder with **Auto detect** or by browsing; the model is chosen on the Models page.
- `llama-server` and `llama-cli` are managed by **two independent processes**. The status card shows a separate *Start / Stop* button for each: start one, start both, or stop one without affecting the other.
- Switching the run mode only changes which parameters are edited; it never starts or stops the other process.
- The parameter centre groups options into Common / Sampling / Performance / Cache / Server / Extras / CLI, supports free-text search and mode filtering, and offers a custom-parameter field plus a live command-line preview and a raw log.
- **Run in background** hides the main window and keeps the service alive in the tray.

### 5.5 Models workspace

Scans `.gguf` files in the configured folder, shows size, quantization and modification date, and lets you set the current model. Changing the model restarts only the processes that are already running.

### 5.6 Tray and background service

Closing the main window (title-bar **×**) only hides it to the system tray; running services are **not** stopped. Double-click the tray icon, or right-click → *Open main window*, to restore it. Right-click also shows the status of both processes, allows starting / stopping `llama-server`, and offers *Quit and stop services*, which is the only way to terminate both processes and exit.

On Windows 11 a new tray icon may be folded into the `^` overflow panel; enable it in the taskbar settings if it is not immediately visible.

## 6. Calling the API from other applications

Once `llama-server` is running, the OpenAI-compatible endpoint is `http://127.0.0.1:8080/v1/chat/completions` (host, port and optional API key are configurable; the current base URL and ready-to-copy `curl` / Python examples are shown on the Service page).

```python
import json, urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8080/v1/chat/completions",
    data=json.dumps({
        "model": "local-model",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
    }).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(req).read().decode("utf-8"))
```

## 7. Files and data

| Path | Purpose |
| --- | --- |
| `LlamaGUI.exe` | Main launcher (< 1 MB, no console) |
| `uninstall.exe` | Uninstaller |
| `first_run.bat` | All-English first-time installer |
| `main.py` | Python entry point |
| `app/` | Application modules |
| `tools/` | Installer helpers, icon and launcher builders |
| `assets/` | Application icons (`.ico`) |
| `.venv/` | Virtual environment, created by `first_run.bat` |
| `llama_gui_config.json` | Service parameters, theme, appearance, model paths |
| `data/sessions.json` | Projects, conversations, messages, prompts |
| `requirements.txt` | `PySide6>=6.6,<7` |

## 8. Uninstall

Run **`uninstall.exe`**. It offers three choices:

- **Yes** — full uninstall: dependencies, caches and all program files are removed (the folder is deleted after the process exits);
- **No** — environment-only cleanup: source files are kept and `first_run.bat` restores a complete installation;
- **Cancel** — no changes.

## 9. Environment variables (optional, for unattended setup)

| Variable | Effect |
| --- | --- |
| `LLAMA_SILENT` | Skip the final *Press any key* prompt |
| `LLAMA_PY_INDEX` | Pre-select a Python by number when several are installed |
| `LLAMA_PIP_INDEX` | Force one package index and skip the speed test |
| `LLAMA_CPP_DIR` / `LLAMA_DIR` / `LLAMA_SERVER_DIR` | Hint for locating the llama.cpp folder |

A `llama_dir.txt` file in the program folder can hold the same directory hint.

## 10. Notes and troubleshooting

- **Moving to another computer**: copy the whole folder and re-run `first_run.bat`. It rebuilds `.venv` and the three executables for that machine. `llama_gui_config.json` may still contain absolute paths to the previous computer's llama.cpp folder and models; use **Auto detect** on the Service page and reselect the model.
- **Icons**: the exe, taskbar, Task Manager and tray all use the same custom icon. If Windows still shows a cached Python icon, rebuilding via `first_run.bat` refreshes the executables; a sign-out refreshes the shell icon cache.
- **All indexes failed**: set `LLAMA_PIP_INDEX` to a reachable index and run `first_run.bat` again.
- **No Python found**: install 64-bit Python 3.9+ from python.org, then run `first_run.bat` again.
- The chat and terminal views wrap long lines automatically; no horizontal scrolling is needed.

## 11. What is new in v0.0.4

Conversation / project manager with archive and per-conversation prompts; gear-icon appearance settings; all-English six-step installer with Python detection, mirror benchmarking and automatic virtual-environment repair. Everything else follows v0.0.3: tray background service, independent dual processes, custom icons and launchers below 1 MB.

---

# 中文

**版本：v0.0.4**（Windows 10 / 11，Python + PySide6，2026-11-06）

以下为中文说明，与上文英文内容一一对应。

## 1. 软件简介

Llama Studio 是 **llama.cpp** 的本地图形界面前端，主要功能：

- **对话**：通过 `llama-server` 的 OpenAI 兼容 HTTP API 进行流式对话（显示 token 速率、首 token 延迟等指标），也可通过 `llama-cli` 的本地终端直连交互；
- **开启服务**：启动 `llama-server` 供其他软件调用 API，支持隐藏界面、仅驻留系统托盘；
- **对话窗口管理**：项目（可包含多个对话）、临时对话，以及归档、删除、移动、重命名；
- **每个对话独立的系统提示词**，以及可自定义的外观（主题、强调色、背景、毛玻璃、字号）；
- **参数中心**：分组、搜索、按运行模式过滤、命令行实时预览。

软件**不包含** llama.cpp 可执行文件和模型文件，需自行准备 `llama-server.exe` / `llama-cli.exe` 与 `.gguf` 模型。

## 2. 运行环境

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows 10 / 11，64 位 |
| Python | 3.9 及以上、64 位 CPython（会忽略 WindowsApps 别名、MinGW 构建与 32 位版本） |
| 依赖包 | `PySide6 >= 6.6, < 7`，由 `first_run.bat` 自动安装 |
| llama.cpp | 含 `llama-server.exe` 与 `llama-cli.exe` 的发行目录 |
| 模型 | 一个或多个 `.gguf` 文件 |

## 3. 首次安装

1. 将 **整个** `v0.0.4` 文件夹复制到任意位置；支持带空格的路径，代码中不含绝对路径。
2. 双击 **`first_run.bat`**。全部提示为英文，按 `[1]`—`[6]` 依次执行：

| 步骤 | 内容 |
| --- | --- |
| `[1]` | 检测本机可用 Python。**未检测到** → 自动打开 `https://www.python.org/downloads/` 并退出；**仅一个** → 直接使用；**多个** → 列出编号供选择。 |
| `[2]` | 用所选解释器创建 `.venv`；若已有虚拟环境失效或版本不符（例如从另一台电脑整体复制），自动重建。 |
| `[3]` | 并发测速 7 个 PyPI 源（官方、清华、阿里、中科大、腾讯、华为、豆瓣），按响应时间排序。 |
| `[4]` | 从最快的源安装 `requirements.txt`；失败时自动切换到排序中的下一个源。 |
| `[5]` | 按本机解释器重建 `LlamaGUI.exe`、`uninstall.exe`、`.venv\Scripts\LlamaRuntime.exe` 与自定义图标。 |
| `[6]` | `Setup complete.`，安装完成。 |

3. 双击 **`LlamaGUI.exe`** 启动。

`LlamaGUI.exe` 是轻量启动器（小于 1 MB），**不是单文件打包程序**：它调用本目录 `.venv` 运行 `main.py`，运行时不显示控制台。请勿把 exe 单独移出文件夹，否则无法启动。

## 4. 启动方式

| 命令 | 效果 |
| --- | --- |
| `LlamaGUI.exe` | 正常启动并显示主窗口 |
| `LlamaGUI.exe --tray` | 不显示主窗口，仅驻留托盘 |
| `LlamaGUI.exe --tray --start-server` | 无界面启动，并自动拉起 `llama-server` |
| `.venv\Scripts\python.exe main.py` | 手动启动，便于调试（会显示控制台） |

使用参数时，创建 Windows 快捷方式并在「目标」后追加参数，例如 `"...\LlamaGUI.exe" --tray --start-server`。

## 5. 使用说明

### 5.1 左侧对话窗口管理（位于「对话 / 服务 / 模型」下方）

- **＋** 打开「新建对话」对话框：可设定对话名称、归属项目（可现场新建，或选择「临时对话（不归入项目）」）以及**本对话专属的系统提示词**。
- **▣** 新建项目；一个项目可容纳多个对话，支持折叠、重命名、删除（删除项目后其中对话转为临时对话）。
- 每个对话右侧 **⋯** 菜单：重命名、移动到项目、归档 / 取消归档、删除；归档内容在底部「已归档」中展开恢复。
- 点击条目即切换对话：先把当前消息与提示词写回旧会话，再载入新会话，互不串扰；首条消息自动作为对话标题。
- 数据保存在 `data/sessions.json`，编辑后防抖自动保存，重启不丢失。

### 5.2 每个对话独立的系统提示词

对话页默认展开「系统提示词（仅作用于当前对话，每次请求都会携带）」卡片，修改即时生效并保存到该会话；标题栏右侧「系统提示词」按钮可收起 / 展开。不同对话的提示词互不影响。

### 5.3 右上角设置（标题栏齿轮）

设置对话框为非模态，改动即时生效并自动保存。可调整：浅色 / 深色主题、毛玻璃效果、背景不透明度、界面字号、强调色（7 个预设 + 自定义）、窗口背景色、面板 / 卡片背景色、用户气泡颜色、背景图片，以及「恢复默认」。文字与边框颜色会依据背景亮度自动派生，深色背景不会出现黑字黑底。

### 5.4 服务窗口

- 用「自动探测」或手动选择 llama.cpp 目录；模型在「模型」页选择。
- `llama-server` 与 `llama-cli` 由**两个相互独立的进程**管理：状态卡中两行各带独立的「启动 / 停止」按钮，可以只开一个、同时开两个，或单独停止其中一个而不影响另一个。
- 切换运行模式只改变当前编辑的参数集合，不会启停另一个进程。
- 参数中心按常用 / 采样 / 性能 / 缓存 / 服务 / 扩展 / CLI 分组，支持搜索、按模式过滤、自定义参数、命令行预览与运行日志。
- 「后台运行」隐藏主界面，服务继续在托盘中运行。

### 5.5 模型窗口

递归扫描指定目录下的 `.gguf` 文件，显示体积、量化格式与修改日期，点击卡片设为当前模型；切换模型只重启当前已运行的进程。

### 5.6 托盘与后台服务

点击标题栏 **×** 只是隐藏到系统托盘，**不会停止服务**。双击托盘图标或右键「打开主界面」可恢复窗口；右键菜单还显示两个进程状态、可单独启停 `llama-server`，以及「退出并停止服务」——只有这一项会结束两个进程并真正退出。

Windows 11 可能把新托盘图标折叠进 `^` 面板，可在任务栏设置中改为显示。

## 6. 供其他软件调用 API

`llama-server` 启动后，OpenAI 兼容端点为 `http://127.0.0.1:8080/v1/chat/completions`（地址、端口与可选 API Key 均可配置；服务页显示当前 API 地址，并提供可复制的 curl / Python 示例）。

```python
import json, urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8080/v1/chat/completions",
    data=json.dumps({
        "model": "local-model",
        "messages": [{"role": "user", "content": "你好"}],
        "stream": False,
    }).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(req).read().decode("utf-8"))
```

## 7. 文件与数据

| 路径 | 用途 |
| --- | --- |
| `LlamaGUI.exe` | 主启动器（< 1 MB，无控制台） |
| `uninstall.exe` | 卸载程序 |
| `first_run.bat` | 全英文首次安装脚本 |
| `main.py` | Python 入口 |
| `app/` | 程序模块 |
| `tools/` | 安装辅助脚本、图标与启动器构建工具 |
| `assets/` | 程序图标 `.ico` |
| `.venv/` | 由 `first_run.bat` 创建的虚拟环境 |
| `llama_gui_config.json` | 服务参数、主题、外观、模型路径 |
| `data/sessions.json` | 项目、对话、消息、提示词 |
| `requirements.txt` | `PySide6>=6.6,<7` |

## 8. 卸载

运行 **`uninstall.exe`**，弹出三种选择：

- **是(Y)** — 完整卸载：清理依赖与缓存，并在程序退出后删除整个文件夹；
- **否(N)** — 仅清理环境：保留源码，之后重新运行 `first_run.bat` 即可恢复；
- **取消** — 不做任何改动。

## 9. 可选环境变量（无人值守安装）

| 变量 | 作用 |
| --- | --- |
| `LLAMA_SILENT` | 跳过末尾「按任意键继续」 |
| `LLAMA_PY_INDEX` | 多版本 Python 时预先指定编号 |
| `LLAMA_PIP_INDEX` | 强制使用指定安装源，跳过测速 |
| `LLAMA_CPP_DIR` / `LLAMA_DIR` / `LLAMA_SERVER_DIR` | 提示 llama.cpp 所在目录 |

也可在程序目录放置 `llama_dir.txt`，写入同一目录路径。

## 10. 注意事项与问题排查

- **复制到另一台电脑**：整体复制文件夹后重新运行 `first_run.bat`，会按新机器重建 `.venv` 与三个 exe。`llama_gui_config.json` 中的 llama.cpp 目录和模型路径可能是原电脑的绝对路径，请在服务页点「自动探测」并在模型页重新选择。
- **图标**：exe、任务栏、任务管理器与托盘共用同一套自定义图标。若 Windows 仍显示缓存的 Python 图标，重新运行 `first_run.bat` 可重建 exe，注销一次可刷新系统图标缓存。
- **所有安装源均失败**：设置 `LLAMA_PIP_INDEX` 指向可访问的源后重跑 `first_run.bat`。
- **未检测到 Python**：先到 python.org 安装 64 位 Python 3.9+，再重跑脚本。
- 对话气泡与 CLI 终端均自动换行，无需左右拖动。

## 11. v0.0.4 更新内容

新增对话 / 项目管理（归档、移动、临时对话）与每个对话独立的系统提示词；新增右上角齿轮外观设置；`first_run.bat` 改为全英文六步流程，加入 Python 环境检测、多源测速与虚拟环境自动修复。其余沿用 v0.0.3：托盘后台服务、双进程独立启停、自定义图标与小于 1 MB 的启动器。
