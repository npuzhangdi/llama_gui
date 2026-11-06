# -*- coding: utf-8 -*-
"""Llama Studio 入口。

所有路径相对本文件解析，程序目录可整体移动到任意位置。
由 LlamaGUI.exe 通过本目录 .venv 的 LlamaRuntime.exe 启动，不显示控制台。

可选命令行参数（创建快捷方式时使用，路径仍相对）：
    --tray           启动后不显示主窗口，直接驻留系统托盘
    --start-server   启动后自动拉起 llama-server（常与 --tray 合用）
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import Config
from app.theme import build_qss, palette
from app.tray import AppTray
from app.window import MainWindow

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "assets" / "app.ico"
APP_ID = "LlamaStudio.App.3"


def main() -> None:
    args = sys.argv[1:]
    tray_only = "--tray" in args
    start_server = "--start-server" in args

    # 必须在任何窗口创建前设置：任务栏按此 ID 分组，并使用本程序图标
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Llama Studio")
    app.setApplicationDisplayName("Llama Studio")
    # 主窗口隐藏后事件循环保持运行，托盘仍可响应
    app.setQuitOnLastWindowClosed(False)

    icon = QIcon(str(ICON)) if ICON.is_file() else QIcon()
    app.setWindowIcon(icon)

    cfg = Config()
    app.setStyleSheet(build_qss(palette(str(cfg.get("theme")))))

    win = MainWindow(cfg)
    win.setWindowIcon(icon)
    tray = AppTray(icon, app)
    win.attach_tray(tray)

    tray.show_requested.connect(win.restore_from_tray)
    tray.quit_requested.connect(win.quit_application)
    tray.server_toggle.connect(win.toggle_server_from_tray)
    for proc in (win.proc_server, win.proc_cli):
        proc.state_changed.connect(
            lambda _s: tray.update_status(win.proc_server.is_running(),
                                          win.proc_cli.is_running()))
    tray.update_status(False, False)

    if not tray_only:
        win.show()
    elif not tray.available:
        # 系统不支持托盘时不能无界面运行，否则用户无法找回程序
        win.show()

    if start_server:
        QTimer.singleShot(400, lambda: win.service.start_process("llama-server"))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
