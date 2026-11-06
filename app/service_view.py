# -*- coding: utf-8 -*-
"""服务视图：双模式启动、参数分级、命令行预览、API 接入示例与运行日志。"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .config import Config
from .core import ADV_PARAMS, MAIN_PARAMS, ProcManager, build_args, preview_command
from .theme import Palette
from .widgets import Card, Collapsible, PathRow, SectionHeader, Segmented, ToggleSwitch


class Field(QWidget):
    """标签 + 输入控件的一行。"""

    def __init__(self, label: str, control: QWidget, parent=None):
        super().__init__(parent)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(9)
        lab = QLabel(label)
        lab.setObjectName("muted")
        lab.setFixedWidth(112)
        box.addWidget(lab)
        box.addWidget(control, 1)


class ServiceView(QWidget):
    program_type_changed = Signal(str)
    state_changed = Signal(str, bool)

    def __init__(self, cfg: Config, proc: ProcManager, pal: Palette, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.proc = proc
        self.pal = pal
        self.controls: dict[str, QWidget] = {}
        self.rows: dict[str, Field] = {}
        self.started_at: float | None = None
        self.last_log = ""
        self.ready = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setFrameShape(QFrame.Shape.NoFrame)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.scroller.setWidget(content)
        outer.addWidget(self.scroller)

        self.scroll_root = QVBoxLayout(content)
        self.scroll_root.setContentsMargins(20, 14, 20, 18)
        self.scroll_root.setSpacing(13)

        head = SectionHeader("服务", pal)
        self.head_state = QLabel("未启动")
        self.head_state.setObjectName("faint")
        head.layout().addWidget(self.head_state)
        self.scroll_root.addWidget(head)

        self.scroll_root.addWidget(self._build_program_card())
        self.scroll_root.addWidget(self._build_status_card())
        self.scroll_root.addWidget(self._build_main_card())
        self.adv = self._build_advanced()
        self.scroll_root.addWidget(self.adv)
        self.scroll_root.addWidget(self._build_preview_card())
        self.logs = self._build_logs()
        self.scroll_root.addWidget(self.logs)
        self.scroll_root.addStretch(1)

        self.proc.output.connect(self.append_log)
        self.proc.state_changed.connect(self.on_proc_state)
        self.proc.finished.connect(lambda _code: self.on_proc_state("idle"))

        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self._tick)
        self.clock.start()

        self.sync_from_config()
        self.set_program_type(str(cfg.get("program_type")), emit=False)
        self.on_proc_state("idle")

    # ---------------- 程序类型 ----------------
    def _build_program_card(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(12)
        label = QLabel("运行模式")
        label.setObjectName("muted")
        label.setFixedWidth(70)
        row.addWidget(label)
        self.segment = Segmented(["llama-server", "llama-cli"], self.pal)
        self.segment.changed.connect(self.set_program_type)
        row.addLayout(self._wrap_widget(self.segment), 1)
        self.mode_note = QLabel("")
        self.mode_note.setObjectName("faint")
        row.addWidget(self.mode_note, 2)
        card.vbox.addLayout(row)

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        plabel = QLabel("程序路径")
        plabel.setObjectName("muted")
        plabel.setFixedWidth(70)
        path_row.addWidget(plabel)
        self.path_row = PathRow(self.pal, "file", "可执行文件 (*.exe);;所有文件 (*)")
        self.path_row.path_changed.connect(self._on_path_changed)
        path_row.addWidget(self.path_row, 1)
        card.vbox.addLayout(path_row)
        return card

    @staticmethod
    def _wrap_widget(widget: QWidget):
        box = QHBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(widget)
        return box

    def _on_path_changed(self, value: str) -> None:
        self.cfg.set_program_path(value)
        self._refresh_preview()

    # ---------------- 状态卡 ----------------
    def _build_status_card(self) -> QWidget:
        card = Card(name="tealcard", margin=18, spacing=12)
        top = QHBoxLayout()
        top.setSpacing(12)
        self.state_dot = QLabel("●")
        self.state_dot.setStyleSheet(f"color: {self.pal.faint}; font-size: 20px;")
        top.addWidget(self.state_dot)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.state_title = QLabel("服务未启动")
        self.state_title.setObjectName("h1")
        titles.addWidget(self.state_title)
        self.state_sub = QLabel("启动 llama-server 后，其他软件即可通过 OpenAI 兼容 API 调用")
        self.state_sub.setObjectName("muted")
        titles.addWidget(self.state_sub)
        top.addLayout(titles, 1)
        self.elapsed_label = QLabel("")
        self.elapsed_label.setObjectName("faint")
        top.addWidget(self.elapsed_label)
        self.start_btn = QPushButton("启动服务")
        self.start_btn.setObjectName("primary")
        self.start_btn.setFixedWidth(112)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.toggle_process)
        top.addWidget(self.start_btn)
        card.vbox.addLayout(top)

        self.api_row = QWidget()
        api = QHBoxLayout(self.api_row)
        api.setContentsMargins(0, 0, 0, 0)
        api.setSpacing(9)
        self.api_label = QLabel(self.cfg.base_url())
        self.api_label.setObjectName("mono")
        api.addWidget(self.api_label, 1)
        self.copy_btn = QPushButton("复制地址")
        self.copy_btn.setFixedWidth(88)
        self.copy_btn.clicked.connect(lambda: self._copy(self.cfg.base_url(), "API 地址已复制"))
        api.addWidget(self.copy_btn)
        self.example_btn = QPushButton("接入示例")
        self.example_btn.setFixedWidth(88)
        self.example_btn.clicked.connect(self._toggle_example)
        api.addWidget(self.example_btn)
        card.vbox.addWidget(self.api_row)

        self.example_box = QPlainTextEdit()
        self.example_box.setObjectName("log")
        self.example_box.setReadOnly(True)
        self.example_box.setFixedHeight(150)
        self.example_box.setVisible(False)
        card.vbox.addWidget(self.example_box)

        self.recent = QLabel("")
        self.recent.setObjectName("faint")
        card.vbox.addWidget(self.recent)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {self.pal.danger};")
        card.vbox.addWidget(self.error_label)
        self.error_label.setVisible(False)
        return card

    def _toggle_example(self) -> None:
        visible = not self.example_box.isVisible()
        self.example_box.setVisible(visible)
        if visible:
            self._refresh_examples()

    def _refresh_examples(self) -> None:
        url = self.cfg.base_url()
        key = str(self.cfg.get("api_key") or "").strip() or "no-key-required"
        auth = f' \\\n  -H "Authorization: Bearer {key}"' if self.cfg.get("api_key") else ""
        self.example_box.setPlainText(
            "# curl\n"
            f'curl {url}/chat/completions \\\n'
            '  -H "Content-Type: application/json"' + auth + " \\\n"
            '  -d \'{"model":"local-model","messages":[{"role":"user","content":"你好"}],"stream":true}\'\n\n'
            "# Python (openai sdk)\n"
            "from openai import OpenAI\n"
            f'client = OpenAI(base_url="{url}", api_key="{key}")\n'
            'resp = client.chat.completions.create(\n'
            '    model="local-model",\n'
            '    messages=[{"role": "user", "content": "你好"}],\n'
            ")\n"
            "print(resp.choices[0].message.content)"
        )

    def _copy(self, text: str, tip: str) -> None:
        QApplication.clipboard().setText(text)
        self.recent.setText(tip)

    # ---------------- 参数卡片 ----------------
    def _control_for(self, spec):
        if spec.kind == "combo":
            combo = QComboBox()
            combo.addItems(list(spec.options))
            combo.currentTextChanged.connect(lambda _v, k=spec.key: self._on_param(k))
            return combo
        if spec.kind == "bool":
            switch = ToggleSwitch(self.pal)
            switch.toggled.connect(lambda _v, k=spec.key: self._on_param(k))
            return switch
        if spec.kind == "file":
            row = PathRow(self.pal, "file", "所有文件 (*)")
            row.path_changed.connect(lambda _v, k=spec.key: self._on_param(k))
            return row
        edit = QLineEdit()
        edit.setPlaceholderText(spec.placeholder)
        edit.textChanged.connect(lambda _v, k=spec.key: self._on_param(k))
        return edit

    def _value_of(self, spec):
        widget = self.controls[spec.key]
        if spec.kind == "combo":
            return widget.currentText()
        if spec.kind == "bool":
            return widget.isChecked()
        if spec.kind == "file":
            return widget.text()
        return widget.text().strip()

    def _set_value_of(self, spec, value) -> None:
        widget = self.controls[spec.key]
        if spec.kind == "combo":
            widget.blockSignals(True)
            index = widget.findText(str(value or ""))
            widget.setCurrentIndex(index if index >= 0 else 0)
            widget.blockSignals(False)
        elif spec.kind == "bool":
            widget.blockSignals(True)
            widget.setChecked(bool(value))
            widget.blockSignals(False)
        elif spec.kind == "file":
            widget.blockSignals(True)
            widget.set_text(str(value or ""))
            widget.blockSignals(False)
        else:
            widget.blockSignals(True)
            widget.setText(str(value or ""))
            widget.blockSignals(False)

    def _on_param(self, _key: str) -> None:
        for spec in MAIN_PARAMS + ADV_PARAMS:
            self.cfg.set(spec.key, self._value_of(spec))
        self._refresh_preview()
        self._refresh_examples_if_visible()

    def _refresh_examples_if_visible(self) -> None:
        if self.example_box.isVisible():
            self._refresh_examples()
        self.api_label.setText(self.cfg.base_url())

    def _add_fields(self, host_layout, specs, columns: int = 2) -> None:
        if isinstance(host_layout, QGridLayout):
            for idx, spec in enumerate(specs):
                control = self._control_for(spec)
                self.controls[spec.key] = control
                field = Field(spec.label, control)
                self.rows[spec.key] = field
                host_layout.addWidget(field, idx // columns, idx % columns)
        else:
            for spec in specs:
                control = self._control_for(spec)
                self.controls[spec.key] = control
                field = Field(spec.label, control)
                self.rows[spec.key] = field
                host_layout.addWidget(field)

    def _build_main_card(self) -> QWidget:
        card = Card()
        title = QLabel("常用参数")
        title.setObjectName("h2")
        card.vbox.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(11)
        grid.setContentsMargins(0, 0, 0, 0)
        self._add_fields(grid, MAIN_PARAMS)
        card.vbox.addLayout(grid)
        return card

    def _build_advanced(self) -> QWidget:
        outer = QWidget()
        box = QVBoxLayout(outer)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        fold = Collapsible("高级参数", self.pal, subtitle="默认折叠，全部保留但不干扰主界面")
        grid = QGridLayout()
        grid.setSpacing(11)
        grid.setContentsMargins(0, 0, 0, 0)
        self._add_fields(grid, ADV_PARAMS)
        fold.vbox.addLayout(grid)

        custom_row = QHBoxLayout()
        custom_row.setSpacing(9)
        clabel = QLabel("自定义参数")
        clabel.setObjectName("muted")
        clabel.setFixedWidth(112)
        custom_row.addWidget(clabel)
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("额外参数，空格分隔，引号可包裹含空格的路径")
        self.custom_edit.textChanged.connect(lambda: (self.cfg.set("custom", self.custom_edit.text()), self._refresh_preview()))
        custom_row.addWidget(self.custom_edit, 1)
        fold.vbox.addLayout(custom_row)
        box.addWidget(fold)
        self.adv_fold = fold
        return outer

    def _build_preview_card(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(8)
        title = QLabel("命令行预览")
        title.setObjectName("h2")
        row.addWidget(title)
        row.addStretch(1)
        copy = QPushButton("复制命令")
        copy.setFixedWidth(88)
        copy.clicked.connect(lambda: self._copy(preview_command(self.cfg.program_path(), build_args(self.cfg)), "命令已复制"))
        row.addWidget(copy)
        card.vbox.addLayout(row)
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("log")
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(58)
        card.vbox.addWidget(self.preview)
        return card

    def _build_logs(self) -> QWidget:
        fold = Collapsible("运行日志", self.pal, subtitle="llama.cpp 原始输出")
        self.log_edit = QPlainTextEdit()
        self.log_edit.setObjectName("log")
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(600)
        self.log_edit.setFixedHeight(190)
        fold.vbox.addWidget(self.log_edit)
        bar = QHBoxLayout()
        bar.addStretch(1)
        clear = QPushButton("清空日志")
        clear.clicked.connect(self.log_edit.clear)
        bar.addWidget(clear)
        fold.vbox.addLayout(bar)
        return fold

    # ---------------- 同步 ----------------
    def sync_from_config(self) -> None:
        for spec in MAIN_PARAMS + ADV_PARAMS:
            if spec.key in self.controls:
                self._set_value_of(spec, self.cfg.get(spec.key))
        self.custom_edit.blockSignals(True)
        self.custom_edit.setText(str(self.cfg.get("custom", "") or ""))
        self.custom_edit.blockSignals(False)
        self.path_row.blockSignals(True)
        self.path_row.set_text(self.cfg.program_path())
        self.path_row.blockSignals(False)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        self.preview.setPlainText(preview_command(self.cfg.program_path(), build_args(self.cfg)))
        self.api_label.setText(self.cfg.base_url())

    def set_program_type(self, value: str, emit: bool = True) -> None:
        value = "llama-cli" if value == "llama-cli" else "llama-server"
        self.cfg.set("program_type", value)
        self.segment.select(value)
        is_cli = value == "llama-cli"
        self.mode_note.setText("本地交互，不提供 HTTP API" if is_cli else "OpenAI 兼容 API，可对外提供服务")
        for spec in MAIN_PARAMS + ADV_PARAMS:
            field = self.rows.get(spec.key)
            if field is not None:
                field.setVisible(spec.server if not is_cli else spec.cli)
        self.api_row.setVisible(not is_cli)
        if is_cli:
            self.example_box.setVisible(False)
        self.path_row.blockSignals(True)
        self.path_row.set_text(self.cfg.program_path())
        self.path_row.blockSignals(False)
        self.start_btn.setText("启动 CLI" if is_cli else "启动服务")
        self.state_sub.setText("通过标准输入与 llama-cli 交互" if is_cli
                               else "启动 llama-server 后，其他软件即可通过 OpenAI 兼容 API 调用")
        self._refresh_preview()
        if emit:
            self.program_type_changed.emit(value)

    # ---------------- 进程 ----------------
    def toggle_process(self) -> None:
        if self.proc.is_running():
            self.proc.stop()
        else:
            self.start_process()

    def start_process(self) -> bool:
        self.error_label.setVisible(False)
        self.log_edit.clear()
        ok, message = self.proc.start(self.cfg.program_path(), build_args(self.cfg))
        if not ok:
            self.error_label.setText(message.replace("\n", " "))
            self.error_label.setVisible(True)
            return False
        self.started_at = time.time()
        self.last_log = ""
        self.recent.setText("进程已启动，等待模型加载…")
        return True

    def restart(self) -> None:
        if self.proc.is_running():
            self.proc.stop()
            QTimer.singleShot(600, self.start_process)
        else:
            self.start_process()

    def on_proc_state(self, state: str) -> None:
        running = state == "running"
        self.start_btn.setText("停止" if running else ("启动 CLI" if self.cfg.get("program_type") == "llama-cli" else "启动服务"))
        self.start_btn.setObjectName("danger" if running else "primary")
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)
        if not running:
            self.started_at = None
            self.ready = False
        self._refresh_status(running)
        self.state_changed.emit(state, self.ready)

    def set_ready(self, ready: bool) -> None:
        if ready != self.ready:
            self.ready = ready
            self._refresh_status(self.proc.is_running())
            self.state_changed.emit("running" if self.proc.is_running() else "idle", ready)

    def _refresh_status(self, running: bool) -> None:
        is_cli = self.cfg.get("program_type") == "llama-cli"
        if running and self.ready:
            title, color = "服务已就绪", self.pal.success
        elif running:
            title, color = "正在加载模型…", self.pal.warn
        else:
            title, color = "服务未启动" if not is_cli else "llama-cli 未启动", self.pal.faint
        self.state_title.setText(title)
        self.state_dot.setStyleSheet(f"color: {color}; font-size: 20px;")
        self.head_state.setText("运行中" if running else "未启动")
        self.elapsed_label.setText("")
        if running:
            self._tick()

    def _tick(self) -> None:
        if self.started_at and self.proc.is_running():
            secs = int(time.time() - self.started_at)
            self.elapsed_label.setText(f"已运行 {secs // 60:02d}:{secs % 60:02d}")

    def append_log(self, text: str) -> None:
        clean = text.rstrip()
        if clean:
            self.last_log = clean.splitlines()[-1][:160]
            self.recent.setText(self.last_log)
        self.log_edit.moveCursor(QTextCursor.MoveOperation.End)
        self.log_edit.insertPlainText(text)
        self.log_edit.moveCursor(QTextCursor.MoveOperation.End)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        for key, widget in self.controls.items():
            if isinstance(widget, ToggleSwitch):
                widget.set_palette(pal)
        self.adv_fold.set_palette(pal)
        self.error_label.setStyleSheet(f"color: {pal.danger};")
