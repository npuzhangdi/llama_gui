# -*- coding: utf-8 -*-
"""Llama Studio 入口。

所有路径相对本文件解析，程序目录可整体移动到任意位置。
由 LlamaGUI.exe 通过本目录 .venv 的 pythonw 启动，不显示控制台。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import Config
from app.theme import build_qss, palette
from app.window import MainWindow

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "assets" / "app.ico"


def main() -> None:
    # 让任务栏使用本程序图标而非 Python 默认图标（必须在窗口创建前调用）
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LlamaStudio.App")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Llama Studio")
    app.setApplicationDisplayName("Llama Studio")
    icon = QIcon(str(ICON)) if ICON.is_file() else QIcon()
    app.setWindowIcon(icon)
    app.setStyleSheet("QToolTip { font-family: 'Microsoft YaHei UI'; }")

    cfg = Config()
    app.setStyleSheet(build_qss(palette(str(cfg.get("theme")))))
    win = MainWindow(cfg)
    win.setWindowIcon(icon)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
