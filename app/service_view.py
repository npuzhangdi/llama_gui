# -*- coding: utf-8 -*-
"""服务视图：双模式启动、分组参数中心、命令行预览、API 接入示例与运行日志。"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .config import Config, detect_llama_dir
from .core import (
    ALL_PARAMS, GROUPS, MAIN_PARAMS, OTHER_PARAMS, ProcManager, build_args, preview_command,
)
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
        lab.setFixedWidth(118)
        box.addWidget(lab)
        box.addWidget(control, 1)


class ServiceView(QWidget):
    program_type_changed = Signal(str)
    state_changed = Signal(str, bool)
    llama_dir_changed = Signal()
    background_requested = Signal()   # 隐藏主窗口、驻留托盘，后台进程保持不变

    def __init__(self, cfg: Config, proc_server: ProcManager, proc_cli: ProcManager,
                 pal: Palette, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        # 两个程序由各自的 ProcManager 管理：启动 / 停止 / 状态 / 日志互不影响
        self.managers: dict[str, ProcManager] = {
            "llama-server": proc_server,
            "llama-cli": proc_cli,
        }
        self.pal = pal
        self.controls: dict[str, QWidget] = {}
        self.rows: dict[str, Field] = {}
        self.started_at: dict[str, float | None] = {"llama-server": None, "llama-cli": None}
        self.log_buffers: dict[str, list[str]] = {"llama-server": [], "llama-cli": []}
        self.last_log = ""
        self.ready = False          # 仅表示 llama-server 的 /health 就绪状态
        self.group_keys = {"全部": "all"}
        self.group_keys.update({label: key for key, label in GROUPS})

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
        self.adv = self._build_param_center()
        self.scroll_root.addWidget(self.adv)
        self.scroll_root.addWidget(self._build_preview_card())
        self.logs = self._build_logs()
        self.scroll_root.addWidget(self.logs)
        self.scroll_root.addStretch(1)

        for pt, mgr in self.managers.items():
            mgr.output.connect(lambda text, p=pt: self.append_log(text, p))
            mgr.state_changed.connect(lambda state, p=pt: self.on_proc_state(state, p))
            mgr.finished.connect(lambda _code, p=pt: self.on_proc_state("idle", p))

        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self._tick)
        self.clock.start()

        self.sync_from_config()
        self.set_program_type(str(cfg.get("program_type")), emit=False)
        self.on_proc_state("idle", str(cfg.get("program_type")))

    @property
    def proc(self) -> ProcManager:
        """当前分段选中的模式所对应的进程管理器。"""
        return self.managers[str(self.cfg.get("program_type"))]

    @property
    def proc_server(self) -> ProcManager:
        return self.managers["llama-server"]

    @property
    def proc_cli(self) -> ProcManager:
        return self.managers["llama-cli"]

    # ---------------- 运行模式与程序路径 ----------------
    def _build_program_card(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(12)
        label = QLabel("运行模式")
        label.setObjectName("muted")
        label.setFixedWidth(104)
        row.addWidget(label)
        self.segment = Segmented(["llama-server", "llama-cli"], self.pal)
        self.segment.changed.connect(self.set_program_type)
        row.addLayout(self._wrap_widget(self.segment), 1)
        self.mode_note = QLabel("")
        self.mode_note.setObjectName("faint")
        row.addWidget(self.mode_note, 2)
        card.vbox.addLayout(row)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(10)
        dlabel = QLabel("llama.cpp 目录")
        dlabel.setObjectName("muted")
        dlabel.setFixedWidth(104)
        dir_row.addWidget(dlabel)
        self.llama_row = PathRow(self.pal, "dir")
        self.llama_row.path_changed.connect(self._on_llama_dir_changed)
        dir_row.addWidget(self.llama_row, 1)
        detect = QPushButton("自动探测")
        detect.setObjectName("quiet")
        detect.setFixedWidth(84)
        detect.setCursor(Qt.CursorShape.PointingHandCursor)
        detect.setToolTip("依次从环境变量、llama_dir.txt、PATH 与程序相邻目录查找 llama-server.exe")
        detect.clicked.connect(self._on_detect)
        dir_row.addWidget(detect)
        card.vbox.addLayout(dir_row)

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        plabel = QLabel("程序路径")
        plabel.setObjectName("muted")
        plabel.setFixedWidth(104)
        path_row.addWidget(plabel)
        self.path_row = PathRow(self.pal, "file", "可执行文件 (*.exe);;所有文件 (*)")
        self.path_row.path_changed.connect(self._on_path_changed)
        path_row.addWidget(self.path_row, 1)
        card.vbox.addLayout(path_row)

        hint = QLabel("换电脑后只需在此选择 llama.cpp 目录，两个可执行文件与模型扫描目录会自动补全；所有程序内路径均为相对路径。")
        hint.setObjectName("faint")
        hint.setWordWrap(True)
        card.vbox.addWidget(hint)
        return card

    @staticmethod
    def _wrap_widget(widget: QWidget):
        box = QHBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(widget)
        return box

    def _on_path_changed(self, value: str) -> None:
        self.cfg.set_program_path(value)
        folder = str(self.cfg.get("llama_dir", "") or "")
        self.llama_row.blockSignals(True)
        self.llama_row.set_text(folder)
        self.llama_row.blockSignals(False)
        self._refresh_preview()

    def _on_llama_dir_changed(self, value: str) -> None:
        self.cfg.set_llama_dir(value)
        self.path_row.blockSignals(True)
        self.path_row.set_text(self.cfg.program_path())
        self.path_row.blockSignals(False)
        self.llama_dir_changed.emit()
        self._refresh_preview()

    def _on_detect(self) -> None:
        found = detect_llama_dir()
        if not found:
            self.error_label.setText(
                "未自动探测到 llama-server.exe。请手动选择 llama.cpp 目录，"
                "或设置环境变量 LLAMA_CPP_DIR / 在程序目录放 llama_dir.txt。"
            )
            self.error_label.setVisible(True)
            return
        self.error_label.setVisible(False)
        self.llama_row.blockSignals(True)
        self.llama_row.set_text(found)
        self.llama_row.blockSignals(False)
        self._on_llama_dir_changed(found)
        self.recent.setText(f"已探测到 llama.cpp 目录：{found}")

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
        self.bg_btn = QPushButton("后台运行")
        self.bg_btn.setObjectName("quiet")
        self.bg_btn.setFixedWidth(92)
        self.bg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bg_btn.setToolTip("隐藏主界面并驻留右下角托盘，服务继续运行；\n"
                               "右键托盘图标可打开主界面或退出程序")
        self.bg_btn.clicked.connect(self.background_requested.emit)
        top.addWidget(self.bg_btn)
        card.vbox.addLayout(top)

        # 两种程序各自的状态与独立启停按钮，无需切换运行模式即可分别控制
        dual = QHBoxLayout()
        dual.setSpacing(10)
        self.dual_labels: dict[str, QLabel] = {}
        self.dual_buttons: dict[str, QPushButton] = {}
        for pt in ("llama-server", "llama-cli"):
            lab = QLabel(f"● {pt}  未启动")
            lab.setObjectName("faint")
            self.dual_labels[pt] = lab
            dual.addWidget(lab)
            btn = QPushButton("启动")
            btn.setObjectName("mini")
            btn.setFixedWidth(62)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"独立启动 / 停止 {pt}，不影响另一个程序")
            btn.clicked.connect(lambda _=False, p=pt: self.toggle_process_for(p))
            self.dual_buttons[pt] = btn
            dual.addWidget(btn)
        note = QLabel("两者相互独立，可分别启停、同时运行")
        note.setObjectName("faint")
        dual.addWidget(note, 1)
        card.vbox.addLayout(dual)

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
        self.error_label.setWordWrap(True)
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

    # ---------------- 参数控件 ----------------
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
        if spec.kind in ("file", "dir"):
            row = PathRow(self.pal, "file" if spec.kind == "file" else "dir", "所有文件 (*)")
            row.path_changed.connect(lambda _v, k=spec.key: self._on_param(k))
            return row
        edit = QLineEdit()
        edit.setPlaceholderText(spec.placeholder)
        edit.setToolTip(f"{spec.flag}  ·  {spec.placeholder}")
        edit.textChanged.connect(lambda _v, k=spec.key: self._on_param(k))
        return edit

    def _value_of(self, spec):
        widget = self.controls[spec.key]
        if spec.kind == "combo":
            return widget.currentText()
        if spec.kind == "bool":
            return widget.isChecked()
        if spec.kind in ("file", "dir"):
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
        elif spec.kind in ("file", "dir"):
            widget.blockSignals(True)
            widget.set_text(str(value or ""))
            widget.blockSignals(False)
        else:
            widget.blockSignals(True)
            widget.setText(str(value or ""))
            widget.blockSignals(False)

    def _on_param(self, _key: str) -> None:
        for spec in ALL_PARAMS:
            self.cfg.set(spec.key, self._value_of(spec))
        self._refresh_preview()
        self._refresh_examples_if_visible()

    def _refresh_examples_if_visible(self) -> None:
        if self.example_box.isVisible():
            self._refresh_examples()
        self.api_label.setText(self.cfg.base_url())

    def _add_fields(self, host_layout, specs, columns: int = 2) -> None:
        for idx, spec in enumerate(specs):
            control = self._control_for(spec)
            self.controls[spec.key] = control
            field = Field(spec.label, control)
            field.setToolTip(f"{spec.flag}  ·  {spec.placeholder}")
            self.rows[spec.key] = field
            host_layout.addWidget(field, idx // columns, idx % columns)

    def _build_main_card(self) -> QWidget:
        card = Card()
        title = QLabel("常用参数")
        title.setObjectName("h2")
        card.vbox.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(11)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self._add_fields(grid, MAIN_PARAMS)
        card.vbox.addLayout(grid)
        return card

    def _build_param_center(self) -> QWidget:
        """全部可选参数：分组切换 + 实时搜索 + 自定义参数。"""
        outer = QWidget()
        box = QVBoxLayout(outer)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)

        fold = Collapsible(
            "参数中心", self.pal,
            subtitle=f"共 {len(OTHER_PARAMS)} 项可选参数 · 分组切换 / 搜索 / 按运行模式自动过滤",
        )
        self.param_fold = fold
        self.adv_fold = fold

        toolbar = QHBoxLayout()
        toolbar.setSpacing(9)
        self.param_search = QLineEdit()
        self.param_search.setPlaceholderText("搜索参数名或命令行开关，例如 top_p / -ctk / 缓存")
        self.param_search.setClearButtonEnabled(True)
        self.param_search.textChanged.connect(self._rebuild_params)
        toolbar.addWidget(self.param_search, 1)
        self.param_count = QLabel("")
        self.param_count.setObjectName("muted")
        self.param_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.param_count.setMinimumWidth(215)
        toolbar.addWidget(self.param_count)
        fold.vbox.addLayout(toolbar)

        labels = ["全部"] + [label for _key, label in GROUPS]
        self.group_segment = Segmented(labels, self.pal)
        self.group_segment.changed.connect(self._on_group_changed)
        fold.vbox.addWidget(self.group_segment)
        saved = str(self.cfg.get("param_group", "all") or "all")
        reverse = {v: k for k, v in self.group_keys.items()}
        if saved in reverse and reverse[saved] != "全部":
            self.group_segment.blockSignals(True)
            self.group_segment.select(reverse[saved])
            self.group_segment.blockSignals(False)

        self.param_host = QWidget()
        self.param_grid = QGridLayout(self.param_host)
        self.param_grid.setSpacing(11)
        self.param_grid.setContentsMargins(2, 6, 2, 6)
        self.param_grid.setColumnStretch(0, 1)
        self.param_grid.setColumnStretch(1, 1)
        fold.vbox.addWidget(self.param_host)

        # 所有字段一次性创建，之后仅在网格中重排，避免重复构造控件
        for spec in OTHER_PARAMS:
            control = self._control_for(spec)
            self.controls[spec.key] = control
            field = Field(spec.label, control)
            field.setToolTip(f"{spec.flag}  ·  {spec.placeholder}")
            self.rows[spec.key] = field
            field.setVisible(False)

        self.param_empty = QLabel("没有匹配的参数，试试其它关键词或切换分组。")
        self.param_empty.setObjectName("faint")
        self.param_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.param_empty.setVisible(False)
        fold.vbox.addWidget(self.param_empty)

        custom_row = QHBoxLayout()
        custom_row.setSpacing(9)
        clabel = QLabel("自定义参数")
        clabel.setObjectName("muted")
        clabel.setFixedWidth(118)
        custom_row.addWidget(clabel)
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("额外参数，空格分隔，引号可包裹含空格的路径")
        self.custom_edit.textChanged.connect(
            lambda: (self.cfg.set("custom", self.custom_edit.text()), self._refresh_preview())
        )
        custom_row.addWidget(self.custom_edit, 1)
        fold.vbox.addLayout(custom_row)

        tip = QLabel("留空即使用 llama.cpp 默认值；仅填写的参数会出现在命令行预览中。开关类参数打开后才会追加对应开关。")
        tip.setObjectName("faint")
        tip.setWordWrap(True)
        fold.vbox.addWidget(tip)
        box.addWidget(fold)
        self._rebuild_params()
        return outer

    def _on_group_changed(self, label: str) -> None:
        self.cfg.set("param_group", self.group_keys.get(label, "all"))
        self._rebuild_params()

    def _rebuild_params(self) -> None:
        grid = self.param_grid
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.setVisible(False)
        query = self.param_search.text().strip().lower()
        group = self.group_keys.get(self.group_segment.current, "all")
        is_cli = self.cfg.get("program_type") == "llama-cli"
        usable = [p for p in OTHER_PARAMS if (p.cli if is_cli else p.server)]
        matched = []
        for spec in usable:
            # 有搜索词时跨全部分组检索，避免用户在某个标签下搜不到其它分组的参数
            if not query and group != "all" and spec.group != group:
                continue
            haystack = f"{spec.label} {spec.flag} {spec.key} {spec.placeholder}".lower()
            if query and query not in haystack:
                continue
            matched.append(spec)
        for idx, spec in enumerate(matched):
            field = self.rows[spec.key]
            grid.addWidget(field, idx // 2, idx % 2)
            field.setVisible(True)
        total = len([p for p in ALL_PARAMS if (p.cli if is_cli else p.server)])
        if query:
            self.param_count.setText(f"全部分组搜索到 {len(matched)} 项 / 本模式共 {total} 项")
        else:
            self.param_count.setText(f"本模式共 {total} 项 · 当前显示 {len(matched)} 项")
        self.param_empty.setText("没有匹配的参数，试试其它关键词或清空搜索框。")
        self.param_empty.setVisible(not matched)
        # 通知滚动区内容尺寸变化，避免分组切换后高度未刷新
        self.param_host.updateGeometry()
        host = self.scroller.widget()
        if host is not None:
            host.updateGeometry()

    # ---------------- 预览与日志 ----------------
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
        self.log_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.log_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        for spec in ALL_PARAMS:
            if spec.key in self.controls:
                self._set_value_of(spec, self.cfg.get(spec.key))
        self.custom_edit.blockSignals(True)
        self.custom_edit.setText(str(self.cfg.get("custom", "") or ""))
        self.custom_edit.blockSignals(False)
        self.llama_row.blockSignals(True)
        self.llama_row.set_text(str(self.cfg.get("llama_dir", "") or ""))
        self.llama_row.blockSignals(False)
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
        self.segment.blockSignals(True)
        self.segment.select(value)
        self.segment.blockSignals(False)
        is_cli = value == "llama-cli"
        self.mode_note.setText("本地交互，不提供 HTTP API" if is_cli else "OpenAI 兼容 API，可对外提供服务")
        for spec in MAIN_PARAMS:
            field = self.rows.get(spec.key)
            if field is not None:
                field.setVisible(spec.server if not is_cli else spec.cli)
        self._rebuild_params()
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
        # 仅刷新当前模式的界面状态，绝不启动或停止另一个进程
        self._refresh_log_view(value)
        self.on_proc_state("running" if self.managers[value].is_running() else "idle", value)
        if emit:
            self.program_type_changed.emit(value)

    # ---------------- 进程（两种程序各自独立） ----------------
    def current_type(self) -> str:
        return str(self.cfg.get("program_type"))

    def toggle_process(self) -> None:
        pt = self.current_type()
        mgr = self.managers[pt]
        if mgr.is_running():
            mgr.stop()
        else:
            self.start_process(pt)

    def toggle_process_for(self, program_type: str) -> None:
        """双状态区的独立启停：不改变当前运行模式，也不触碰另一个进程。"""
        if self.managers[program_type].is_running():
            self.stop_process(program_type)
        else:
            self.start_process(program_type)

    def start_process(self, program_type: str | None = None) -> bool:
        """只启动指定模式的进程；另一个程序保持原状。"""
        pt = program_type or self.current_type()
        mgr = self.managers[pt]
        if mgr.is_running():
            return False
        self.error_label.setVisible(False)
        self.log_buffers[pt] = []
        if pt == self.current_type():
            self.log_edit.clear()
        ok, message = mgr.start(self.cfg.program_path(pt), build_args(self.cfg, pt))
        if not ok:
            self.error_label.setText(message.replace("\n", " "))
            self.error_label.setVisible(True)
            return False
        self.started_at[pt] = time.time()
        if pt == self.current_type():
            self.last_log = ""
            self.recent.setText("进程已启动，等待模型加载…")
        return True

    def stop_process(self, program_type: str | None = None) -> None:
        self.managers[program_type or self.current_type()].stop()

    def restart(self) -> None:
        """切换模型后只重启正在运行的程序，不会额外拉起未启动的那个。"""
        for pt, mgr in self.managers.items():
            if mgr.is_running():
                mgr.stop()
                QTimer.singleShot(700, lambda p=pt: self.start_process(p))

    def on_proc_state(self, state: str, program_type: str | None = None) -> None:
        pt = program_type or self.current_type()
        running = state == "running"
        if not running:
            self.started_at[pt] = None
            if pt == "llama-server":
                self.ready = False
        if pt == self.current_type():
            self._refresh_status(running, pt)
        else:
            self._refresh_dual()
            self._refresh_button()
        self.state_changed.emit(state, self.ready)

    def set_ready(self, ready: bool) -> None:
        """仅表示 llama-server 的 /health 状态，与 llama-cli 无关。"""
        if not self.proc_server.is_running():
            ready = False
        if ready != self.ready:
            self.ready = ready
            self._refresh_status(self.proc.is_running(), self.current_type())
            self.state_changed.emit("running" if self.proc.is_running() else "idle", ready)

    def _refresh_button(self) -> None:
        running = self.proc.is_running()
        label = "停止" if running else ("启动 CLI" if self.current_type() == "llama-cli" else "启动服务")
        self.start_btn.setText(label)
        self.start_btn.setObjectName("danger" if running else "primary")
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    def _refresh_dual(self) -> None:
        for pt, lab in self.dual_labels.items():
            # 用状态而非 poll()：点击停止后立即反馈，不必等子进程真正退出
            running = self.managers[pt].state() == "running"
            lab.setText(f"● {pt}  {'运行中' if running else '未启动'}")
            lab.setStyleSheet(f"color: {self.pal.success if running else self.pal.faint};")
            btn = getattr(self, "dual_buttons", {}).get(pt)
            if btn is not None:
                btn.setText("停止" if running else "启动")

    def _refresh_status(self, running: bool, program_type: str | None = None) -> None:
        pt = program_type or self.current_type()
        if pt == "llama-cli":
            title, color = (("llama-cli 运行中", self.pal.success) if running
                            else ("llama-cli 未启动", self.pal.faint))
        elif running and self.ready:
            title, color = "服务已就绪", self.pal.success
        elif running:
            title, color = "正在加载模型…", self.pal.warn
        else:
            title, color = "服务未启动", self.pal.faint
        self.state_title.setText(title)
        self.state_dot.setStyleSheet(f"color: {color}; font-size: 20px;")
        self.head_state.setText("运行中" if running else "未启动")
        self._refresh_dual()
        self._refresh_button()
        self.elapsed_label.setText("")
        if running:
            self._tick()

    def _tick(self) -> None:
        pt = self.current_type()
        start = self.started_at.get(pt)
        if start and self.managers[pt].is_running():
            secs = int(time.time() - start)
            self.elapsed_label.setText(f"已运行 {secs // 60:02d}:{secs % 60:02d}")

    def _refresh_log_view(self, program_type: str) -> None:
        """切换模式时只显示该模式自己的日志，不把两种输出混在一起。"""
        self.log_edit.clear()
        for chunk in self.log_buffers.get(program_type, [])[-600:]:
            self.log_edit.moveCursor(QTextCursor.MoveOperation.End)
            self.log_edit.insertPlainText(chunk)

    def append_log(self, text: str, program_type: str | None = None) -> None:
        pt = program_type or self.current_type()
        self.log_buffers.setdefault(pt, []).append(text)
        if pt != self.current_type():
            return
        clean = text.rstrip()
        if clean:
            self.last_log = clean.splitlines()[-1][:160]
            self.recent.setText(self.last_log)
        self.log_edit.moveCursor(QTextCursor.MoveOperation.End)
        self.log_edit.insertPlainText(text)
        self.log_edit.moveCursor(QTextCursor.MoveOperation.End)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        for widget in self.controls.values():
            if isinstance(widget, ToggleSwitch):
                widget.set_palette(pal)
        self.adv_fold.set_palette(pal)
        self.logs.set_palette(pal)
        self.error_label.setStyleSheet(f"color: {pal.danger};")
