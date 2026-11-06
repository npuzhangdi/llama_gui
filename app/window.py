# -*- coding: utf-8 -*-
"""主窗口：左侧导航、三视图切换、标题栏模型切换器与全局状态联动。

llama-server 与 llama-cli 各由一个独立的 ProcManager 管理，
两者的启动、停止、日志、就绪状态互不干扰，可同时运行。
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget,
)

from .chat_client import StreamClient
from .chat_view import ChatView
from .config import Config
from .core import ProcManager, probe_health
from .glass import FramelessWindow
from .models_view import ModelsView
from .service_view import ServiceView
from .theme import Palette, build_qss, palette
from .widgets import NavButton


class HealthThread(threading.Thread):
    def __init__(self, cfg: Config, signal):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.signal = signal
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.wait(1.2):
            try:
                self.signal.emit(probe_health(self.cfg.base_url(), 0.5))
            except Exception:
                self.signal.emit(False)

    def stop(self) -> None:
        self.stop_event.set()


class MainWindow(FramelessWindow):
    health_result = Signal(bool)

    def __init__(self, cfg: Config):
        self.cfg = cfg
        pal = palette(str(cfg.get("theme")))
        super().__init__(pal, "Llama Studio")
        self.glass_enabled = bool(cfg.get("glass", True))

        self.proc_server = ProcManager(self)
        self.proc_cli = ProcManager(self)
        self.client = StreamClient(self)
        # 必须最先连接 finished，保证进程引用被清理后其它槽再读状态
        for proc in (self.proc_server, self.proc_cli):
            proc.finished.connect(proc.on_finished)

        self._build_title_widgets()
        self._build_body()

        self.service.program_type_changed.connect(lambda _t: self._sync_mode())
        self.service.state_changed.connect(lambda _s, _r: self._sync_mode())
        self.models.model_changed.connect(self._on_model_changed)
        self.models.restart_requested.connect(self.service.restart)
        self.service.llama_dir_changed.connect(self._on_llama_dir_changed)
        self.chat.request_start.connect(self._start_from_chat)
        self.chat.request_open_service.connect(lambda: self._navigate(1))
        self.model_combo.currentIndexChanged.connect(self._on_combo_changed)

        self.health_result.connect(self._on_health)
        self._health = HealthThread(self.cfg, self.health_result)
        self._health.start()

        for proc in (self.proc_server, self.proc_cli):
            proc.state_changed.connect(self._sync_state_only)
        self._refresh_model_combo()
        self.apply_glass()
        self._sync_mode()

    def manager_for(self, program_type: str) -> ProcManager:
        return self.proc_cli if program_type == "llama-cli" else self.proc_server

    def any_running(self) -> bool:
        return self.proc_server.is_running() or self.proc_cli.is_running()

    def _build_title_widgets(self) -> None:
        lab = QLabel("当前模型")
        lab.setObjectName("faint")
        self.title_bar.center_layout.addWidget(lab)
        self.model_combo = QComboBox()
        self.model_combo.setFixedWidth(268)
        self.model_combo.setToolTip("快速切换模型；运行中切换需重启相应程序")
        self.title_bar.center_layout.addWidget(self.model_combo)
        self.title_bar.center_layout.addStretch(1)

    def _build_body(self) -> None:
        split = QHBoxLayout()
        split.setContentsMargins(12, 4, 12, 12)
        split.setSpacing(10)

        nav = QWidget()
        nav.setFixedWidth(172)
        nav_box = QVBoxLayout(nav)
        nav_box.setContentsMargins(6, 12, 6, 10)
        nav_box.setSpacing(6)
        self.nav_buttons = [
            NavButton("chat", "对话", self.pal),
            NavButton("server", "服务", self.pal),
            NavButton("cube", "模型", self.pal),
        ]
        for idx, btn in enumerate(self.nav_buttons):
            btn.clicked.connect(lambda _=False, i=idx: self._navigate(i))
            nav_box.addWidget(btn)
        nav_box.addStretch(1)

        # 左下角只保留「运行中 / 未启动」状态，不再显示效果标注文字
        self.run_label = QLabel("● 未启动")
        self.run_label.setObjectName("faint")
        nav_box.addWidget(self.run_label)

        self.stack = QStackedWidget()
        self.chat = ChatView(self.cfg, self.proc_cli, self.client, self.pal)
        self.service = ServiceView(self.cfg, self.proc_server, self.proc_cli, self.pal)
        self.models = ModelsView(self.cfg, self.pal)
        for view in (self.chat, self.service, self.models):
            self.stack.addWidget(view)

        split.addWidget(nav)
        split.addWidget(self.stack, 1)
        self.body_layout.addLayout(split)
        self._navigate(0)

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.set_active(i == index)

    # ---------------- 模型切换 ----------------
    def _refresh_model_combo(self) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for info in self.cfg.scan_models():
            self.model_combo.addItem(info.name, info.path_text)
        current = str(self.cfg.get("model", "") or "")
        idx = self.model_combo.findData(current)
        if idx < 0 and current:
            self.model_combo.addItem(current.replace("\\", "/").split("/")[-1], current)
            idx = self.model_combo.count() - 1
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)

    def _on_combo_changed(self, index: int) -> None:
        if index < 0:
            return
        path = self.model_combo.itemData(index)
        if path:
            self.models.select(str(path))

    def _on_llama_dir_changed(self) -> None:
        """llama.cpp 目录变化后，模型页与标题栏下拉框一并刷新。"""
        self.models.sync_dir()
        self._refresh_model_combo()

    def _on_model_changed(self, path: str) -> None:
        self._refresh_model_combo()
        self.chat.on_model_changed()
        if not self.any_running():
            self.models.tip.setVisible(False)

    # ---------------- 状态联动 ----------------
    def _sync_state_only(self, _state: str) -> None:
        self._sync_mode()

    def _sync_mode(self) -> None:
        program_type = str(self.cfg.get("program_type"))
        # 状态只取当前模式的进程，避免 CLI 运行时把 server 误显示成运行中
        running = self.manager_for(program_type).is_running()
        ready = self.service.ready and program_type == "llama-server"
        self.chat.set_mode(program_type, running, ready)

        any_running = self.any_running()
        self.run_label.setText("● 运行中" if any_running else "● 未启动")
        self.run_label.setStyleSheet(
            f"color: {self.pal.success if any_running else self.pal.faint};"
        )
        self.run_label.setToolTip(
            "llama-server：" + ("运行中" if self.proc_server.is_running() else "未启动")
            + "\nllama-cli：" + ("运行中" if self.proc_cli.is_running() else "未启动")
        )
        self.models.set_running(any_running)

    def _on_health(self, ok: bool) -> None:
        # 就绪状态只由 server 自己的进程决定，与界面当前选中哪个模式无关
        if not self.proc_server.is_running():
            ok = False
        self.service.set_ready(ok)

    def _start_from_chat(self) -> None:
        """CLI 终端页的按钮：只启停 llama-cli，不跳转页面、不触碰 server。"""
        if self.proc_cli.is_running():
            self.service.stop_process("llama-cli")
        else:
            self.service.start_process("llama-cli")

    # ---------------- 主题与毛玻璃 ----------------
    def _on_theme_toggle(self) -> None:
        new_name = "dark" if self.cfg.get("theme") == "light" else "light"
        self.cfg.set("theme", new_name)
        pal: Palette = palette(new_name)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss(pal))
        self.set_palette(pal)
        self.chat.set_palette(pal)
        self.service.set_palette(pal)
        self.models.set_palette(pal)
        for btn in self.nav_buttons:
            btn.set_palette(pal)
        self._sync_mode()

    def toggle_glass(self) -> None:
        super().toggle_glass()
        self.cfg.set("glass", self.glass_enabled)

    # ---------------- 关闭 ----------------
    def closeEvent(self, event) -> None:
        self.cfg.save()
        try:
            self._health.stop()
        except Exception:
            pass
        self.client.cancel()
        self.proc_server.shutdown()
        self.proc_cli.shutdown()
        super().closeEvent(event)
