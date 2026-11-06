# -*- coding: utf-8 -*-
"""系统托盘控制器。

用途：仅运行 llama-server 供其它应用调用时，主窗口可完全隐藏，
程序驻留右下角；右键可打开主界面、单独启停服务、或彻底退出。

托盘图标与窗口图标、exe 图标共用 assets/app.ico 的多尺寸资源。
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class AppTray(QObject):
    show_requested = Signal()
    quit_requested = Signal()
    server_toggle = Signal()

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(parent)
        self.available = bool(QSystemTrayIcon.isSystemTrayAvailable())
        self._tray: QSystemTrayIcon | None = None
        self._first_hide = True
        if not self.available:
            return

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("Llama Studio")

        menu = QMenu()
        menu.addAction("打开主界面", self.show_requested.emit)
        menu.addSeparator()
        self._status = QAction("服务: 未启动  ·  CLI: 未启动", menu)
        self._status.setEnabled(False)
        menu.addAction(self._status)
        menu.addSeparator()
        self._server_action = QAction("启动 llama-server", menu)
        self._server_action.triggered.connect(self.server_toggle.emit)
        menu.addAction(self._server_action)
        menu.addSeparator()
        menu.addAction("退出并停止服务", self.quit_requested.emit)
        self._tray.setContextMenu(menu)
        self._menu = menu
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self.show_requested.emit()

    def update_status(self, server: bool, cli: bool) -> None:
        if not self._tray:
            return
        self._status.setText("服务: %s  ·  CLI: %s" %
                             ("运行中" if server else "未启动",
                              "运行中" if cli else "未启动"))
        self._server_action.setText("停止 llama-server" if server else "启动 llama-server")
        self._tray.setToolTip(
            "Llama Studio\nllama-server: %s\nllama-cli: %s" %
            ("运行中" if server else "未启动", "运行中" if cli else "未启动"))

    def notify_hidden(self) -> None:
        if not self._tray or not self._first_hide:
            return
        self._first_hide = False
        self._tray.showMessage(
            "Llama Studio",
            "主窗口已最小化到系统托盘，后台服务继续运行。\n双击图标或右键可打开主界面。",
            QSystemTrayIcon.MessageIcon.Information, 4000)

    def hide(self) -> None:
        if self._tray:
            self._tray.hide()
