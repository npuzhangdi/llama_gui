# -*- coding: utf-8 -*-
"""Llama Studio 入口。

运行：python main.py
仅依赖 PySide6（HTTP 与配置均使用 Python 标准库）。
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config import Config
from app.theme import build_qss, palette
from app.window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Llama Studio")
    app.setStyleSheet("QToolTip { font-family: 'Microsoft YaHei UI'; }")
    cfg = Config()
    app.setStyleSheet(build_qss(palette(str(cfg.get("theme")))))
    win = MainWindow(cfg)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
