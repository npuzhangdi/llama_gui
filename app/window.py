# -*- coding: utf-8 -*-
"""主窗口：左侧导航、对话窗口管理、三视图切换与全局状态联动。

v0.0.4 新增：
- 左侧「对话窗口」面板：项目（可含多个对话）、临时对话、归档、删除、移动、重命名；
- 每个对话独立保存消息与系统提示词，切换窗口时自动写回 / 载入；
- 标题栏右上角「设置」：主题、颜色、背景、背景图片、不透明度、字号、毛玻璃。

llama-server 与 llama-cli 仍各由一个独立的 ProcManager 管理，互不干扰；
关闭主窗口只隐藏到系统托盘，托盘菜单的「退出」才会停止进程并结束程序。
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .chat_client import StreamClient
from .chat_view import ChatView
from .config import Config, base_dir
from .core import ProcManager, probe_health
from .glass import FramelessWindow
from .models_view import ModelsView
from .service_view import ServiceView
from .session_panel import SessionPanel
from .sessions import SessionStore
from .settings_dialog import AppearanceDialog
from .theme import DEFAULT_APPEARANCE, Palette, build_qss, palette
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
        self.tray = None            # 由 main.py 在构造后注入
        self._closing = False       # 区分「隐藏到托盘」与「真正退出」
        self.settings_dialog: AppearanceDialog | None = None

        self.store = SessionStore()
        self.store.ensure_default(str(cfg.get("system_prompt") or ""))

        appearance = dict(cfg.get("appearance") or {})
        pal = palette(str(cfg.get("theme")), appearance)
        super().__init__(pal, "Llama Studio")
        self.glass_enabled = bool(cfg.get("glass", True))

        # QTimer 需要 QObject 基类已初始化，故放在 super().__init__ 之后
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(450)
        self._save_timer.timeout.connect(self.store.save)

        self.proc_server = ProcManager(self)
        self.proc_cli = ProcManager(self)
        self.client = StreamClient(self)
        # 必须最先连接 finished，保证进程引用被清理后其它槽再读状态
        for proc in (self.proc_server, self.proc_cli):
            proc.finished.connect(proc.on_finished)

        self._build_title_widgets()
        self._build_body()
        self._apply_background_image(appearance)

        self.service.program_type_changed.connect(lambda _t: self._sync_mode())
        self.service.state_changed.connect(lambda _s, _r: self._sync_mode())
        self.models.model_changed.connect(self._on_model_changed)
        self.models.restart_requested.connect(self.service.restart)
        self.service.llama_dir_changed.connect(self._on_llama_dir_changed)
        self.service.background_requested.connect(self.hide_to_tray)
        self.chat.request_start.connect(self._start_from_chat)
        self.chat.request_open_service.connect(lambda: self._navigate(1))
        self.model_combo.currentIndexChanged.connect(self._on_combo_changed)

        # 对话窗口管理
        self.panel.activated.connect(self._activate_session)
        self.panel.changed.connect(self._on_sessions_changed)
        self.chat.request_new_session.connect(self._new_temp_session)
        self.chat.session_dirty.connect(self._persist_current)
        self.chat.prompt_changed.connect(self._on_prompt_changed)
        self.title_bar.settings_clicked.connect(self._open_settings)

        self.health_result.connect(self._on_health)
        self._health = HealthThread(self.cfg, self.health_result)
        self._health.start()

        for proc in (self.proc_server, self.proc_cli):
            proc.state_changed.connect(self._sync_state_only)
        self._refresh_model_combo()
        self.apply_glass()
        self._sync_mode()

        self.chat.load_session(self.store.active())
        self._on_sessions_changed()
        self.panel.refresh()

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
        nav.setFixedWidth(236)
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

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {self.pal.border}; background: {self.pal.border};")
        sep.setFixedHeight(1)
        nav_box.addSpacing(4)
        nav_box.addWidget(sep)
        nav_box.addSpacing(2)

        self.panel = SessionPanel(self.store, self.cfg, self.pal)
        nav_box.addWidget(self.panel, 1)

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

    # ---------------- 对话窗口管理 ----------------
    def _persist_current(self) -> None:
        """把当前视图的消息与提示词写回它所属的会话。"""
        sid = self.chat.session_id
        if not sid or not self.store.get(sid):
            return
        snap = self.chat.snapshot()
        self.store.update_content(sid, snap["messages"], snap["system_prompt"])
        self.panel.refresh()

    def _on_prompt_changed(self, text: str) -> None:
        sid = self.chat.session_id
        if sid:
            self.store.set_prompt(sid, text, save=False)
            self._save_timer.start()

    def _activate_session(self, sid: str) -> None:
        session = self.store.get(sid)
        if not session:
            return
        if self.chat.session_id and self.chat.session_id != sid:
            self._persist_current()
        self.store.set_active(sid)
        self.chat.load_session(session)
        self._on_sessions_changed()
        self._navigate(0)

    def _new_temp_session(self) -> None:
        session = self.store.create_session(
            "", "", str(self.cfg.get("system_prompt") or ""))
        self.panel.refresh()
        self._activate_session(session["id"])

    def _on_sessions_changed(self) -> None:
        session = self.store.active()
        self.chat.set_session_meta(
            str(session.get("title", "新对话")),
            self.store.project_name(str(session.get("project_id", ""))),
        )

    # ---------------- 外观设置 ----------------
    def _open_settings(self) -> None:
        if self.settings_dialog is None:
            dlg = AppearanceDialog(self.cfg, self.pal, self)
            dlg.appearance_changed.connect(self._apply_appearance)
            self.settings_dialog = dlg
        else:
            self.settings_dialog.sync_from_config()
            self.settings_dialog.set_palette(self.pal)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _apply_appearance(self, data: dict) -> None:
        state = dict(data)
        theme = str(state.pop("theme", self.cfg.get("theme")) or "light")
        glass = bool(state.pop("glass", self.cfg.get("glass", True)))
        appearance = {**DEFAULT_APPEARANCE,
                      **{k: v for k, v in state.items() if k in DEFAULT_APPEARANCE}}
        self.cfg.set("theme", theme)
        self.cfg.set("glass", glass)
        self.cfg.set("appearance", appearance)
        self.cfg.save()

        pal: Palette = palette(theme, appearance)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss(pal, appearance.get("font_size") or 13))
        self.glass_enabled = glass
        self.set_palette(pal)
        self.chat.set_palette(pal)
        self.service.set_palette(pal)
        self.models.set_palette(pal)
        self.panel.set_palette(pal)
        for btn in self.nav_buttons:
            btn.set_palette(pal)
        if self.settings_dialog is not None:
            self.settings_dialog.set_palette(pal)
        self._apply_background_image(appearance)
        self._sync_mode()

    def _apply_background_image(self, appearance: dict) -> None:
        rel = str(appearance.get("bg_image") or "")
        if not rel:
            self.set_background_image("")
            return
        candidate = Path(rel)
        if not candidate.is_absolute():
            candidate = base_dir() / candidate
        self.set_background_image(str(candidate) if candidate.is_file() else "")

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
        if self.tray is not None:
            self.tray.update_status(self.proc_server.is_running(),
                                    self.proc_cli.is_running())

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
        state = dict(self.cfg.get("appearance") or {})
        state["theme"] = new_name
        state["glass"] = bool(self.cfg.get("glass", True))
        self._apply_appearance(state)

    def toggle_glass(self) -> None:
        super().toggle_glass()
        self.cfg.set("glass", self.glass_enabled)
        self.cfg.save()
        if self.settings_dialog is not None:
            self.settings_dialog.sync_from_config()

    # ---------------- 托盘 / 关闭 ----------------
    def attach_tray(self, tray) -> None:
        self.tray = tray
        self._sync_mode()

    def hide_to_tray(self) -> None:
        """服务页「后台运行」：只隐藏界面，两个进程保持原状。"""
        if self.tray is None or not self.tray.available:
            self.showMinimized()
            return
        self.hide()
        self.tray.notify_hidden()

    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_server_from_tray(self) -> None:
        """托盘菜单只操作 llama-server，不影响 llama-cli。"""
        if self.proc_server.is_running():
            self.service.stop_process("llama-server")
        else:
            self.service.start_process("llama-server")

    def shutdown_all(self) -> None:
        """真正退出时停止两个进程与后台线程。"""
        try:
            self._health.stop()
        except Exception:
            pass
        self.client.cancel()
        self.proc_server.shutdown()
        self.proc_cli.shutdown()
        if self.tray is not None:
            self.tray.hide()

    def _save_all(self) -> None:
        self._persist_current()
        self._save_timer.stop()
        self.store.save()
        self.cfg.save()

    def quit_application(self) -> None:
        self._closing = True
        self._save_all()
        self.shutdown_all()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event) -> None:
        self._save_all()
        if self._closing:
            super().closeEvent(event)
            return
        if self.tray is not None and self.tray.available:
            # 隐藏而非退出：两个后台进程保持不变，服务仍可被其它应用调用
            event.ignore()
            self.hide()
            self.tray.notify_hidden()
        else:
            self.shutdown_all()
            super().closeEvent(event)
            app = QApplication.instance()
            if app is not None:
                app.quit()
