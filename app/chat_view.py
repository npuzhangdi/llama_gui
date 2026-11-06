# -*- coding: utf-8 -*-
"""对话视图：llama-server 走 HTTP 流式气泡对话，llama-cli 走本地终端直连。"""
from __future__ import annotations

import html
import re

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from .chat_client import StreamClient
from .config import Config
from .core import ProcManager
from .theme import Palette
from .widgets import Card, StatChip

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def render_markdown(text: str, pal: Palette) -> str:
    """极简 Markdown 渲染：代码块、行内代码、粗体、标题、列表、链接、换行。"""
    blocks: list[tuple[str, str]] = []

    def stash(match):
        blocks.append((match.group(1) or "", html.escape(match.group(2).strip("\n"))))
        return f"\x00CODE{len(blocks) - 1}\x00"

    text = re.sub(r"```([\w+-]*)\s*\n(.*?)```", stash, text, flags=re.S)
    text = html.escape(text)
    text = re.sub(
        r"`([^`]+)`",
        lambda m: f'<code style="background-color:{pal.code_bg};color:{pal.code_text};'
                  f'padding:1px 4px;border-radius:4px;">{m.group(1)}</code>',
        text,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?m)^#{1,4}\s+(.+)$", lambda m: f"<b>{m.group(1)}</b><br>", text)
    text = re.sub(r"(?m)^\s*[-*]\s+(.+)$", r"&nbsp;&nbsp;• \1<br>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    text = text.replace("\n", "<br>")
    for idx, (lang, code) in enumerate(blocks):
        head = f'<div style="color:{pal.muted};font-size:11px;">{lang or "code"}</div>' if lang else ""
        block = (
            f'<table width="100%" cellpadding="9" style="background-color:{pal.code_bg};'
            f'border-radius:8px;"><tr><td>{head}'
            f'<pre style="color:{pal.code_text};font-family:Consolas,monospace;'
            f'white-space:pre-wrap;margin:0;">{code}</pre></td></tr></table>'
        )
        text = text.replace(f"\x00CODE{idx}\x00", block)
    return text


class MessageBubble(QFrame):
    """单条消息：头像 + 自适应高度的富文本气泡。"""

    def __init__(self, role: str, pal: Palette, parent=None):
        super().__init__(parent)
        self.role = role
        self.pal = pal
        self.setObjectName("card" if role == "assistant" else "softcard")
        self.setMaximumWidth(760)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        box = QVBoxLayout(self)
        box.setContentsMargins(13, 10, 13, 10)
        box.setSpacing(0)
        self.body = QTextBrowser()
        self.body.setReadOnly(True)
        self.body.setOpenExternalLinks(True)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.document().setDocumentMargin(0)
        box.addWidget(self.body)

        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(12)
        self._fit_timer.timeout.connect(self.fit_height)
        self.body.document().contentsChanged.connect(self._fit_timer.start)

        if role == "user":
            self.setStyleSheet(f"background: {pal.user_bubble}; border: none; border-radius: 14px;")
        self.set_text("")

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        if self.role == "user":
            self.setStyleSheet(f"background: {pal.user_bubble}; border: none; border-radius: 14px;")

    def set_text(self, text: str) -> None:
        self.body.setHtml(f'<div style="color:{self.pal.text};">{text}</div>')
        self.fit_height()

    def fit_height(self) -> None:
        doc = self.body.document()
        width = max(140, self.body.viewport().width())
        doc.blockSignals(True)
        try:
            doc.setTextWidth(width)
            # QTextBrowser 的富文本块自带行距与块边距，留出余量避免末行被裁切
            height = int(doc.size().height()) + 18
        finally:
            doc.blockSignals(False)
        self.body.setFixedHeight(max(30, min(height, 4000)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_timer.start()


class ChatView(QWidget):
    request_start = Signal()
    request_open_service = Signal()

    def __init__(self, cfg: Config, proc: ProcManager, client: StreamClient, pal: Palette, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.proc = proc
        self.client = client
        self.pal = pal
        self.messages: list[dict] = []
        self.content_buffer = ""
        self.reasoning_buffer = ""
        self.current_bubble: MessageBubble | None = None
        self.generating = False
        self.mode = "llama-server"
        self.running = False
        self.ready = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(12)
        root.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_chat_page())
        self.stack.addWidget(self._build_cli_page())
        root.addWidget(self.stack, 1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(45)
        self._refresh_timer.timeout.connect(self._flush_buffer)

        self.client.token.connect(self._on_token)
        self.client.reasoning.connect(self._on_reasoning)
        self.client.stats.connect(self._on_stats)
        self.client.done.connect(self._on_done)
        self.proc.output.connect(self._on_proc_output)
        self.proc.perf.connect(self._on_cli_perf)

        self._welcome()
        self.set_mode(cfg.get("program_type"), False, False)

    # ---------------- 顶部 ----------------
    def _build_header(self) -> QWidget:
        bar = QWidget()
        box = QHBoxLayout(bar)
        box.setContentsMargins(2, 0, 2, 0)
        box.setSpacing(9)
        self.mode_badge = QLabel("HTTP 对话 · llama-server")
        self.mode_badge.setObjectName("badge")
        box.addWidget(self.mode_badge)
        self.model_label = QLabel("")
        self.model_label.setObjectName("faint")
        box.addWidget(self.model_label)
        self.state_label = QLabel("")
        self.state_label.setObjectName("faint")
        box.addWidget(self.state_label)
        box.addStretch(1)

        self.prompt_btn = QPushButton("系统提示词")
        self.prompt_btn.clicked.connect(self._toggle_prompt)
        self.new_btn = QPushButton("新建对话")
        self.new_btn.clicked.connect(self.new_session)
        self.stop_btn = QPushButton("停止生成")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.clicked.connect(self.stop_generation)
        self.stop_btn.setVisible(False)
        for b in (self.prompt_btn, self.new_btn, self.stop_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            box.addWidget(b)
        return bar

    def _toggle_prompt(self) -> None:
        self.prompt_card.setVisible(not self.prompt_card.isVisible())

    # ---------------- HTTP 对话页 ----------------
    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(11)

        self.prompt_card = Card(name="card", margin=12)
        title = QLabel("系统提示词（每次请求都会携带）")
        title.setObjectName("muted")
        self.prompt_card.vbox.addWidget(title)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setFixedHeight(58)
        self.prompt_edit.setPlainText(str(self.cfg.get("system_prompt", "")))
        self.prompt_edit.textChanged.connect(
            lambda: self.cfg.set("system_prompt", self.prompt_edit.toPlainText())
        )
        self.prompt_card.vbox.addWidget(self.prompt_edit)
        self.prompt_card.setVisible(False)
        box.addWidget(self.prompt_card)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.messages_host = QWidget()
        self.msg_layout = QVBoxLayout(self.messages_host)
        self.msg_layout.setContentsMargins(4, 4, 8, 12)
        self.msg_layout.setSpacing(14)
        self.msg_layout.addStretch(1)
        self.scroll.setWidget(self.messages_host)
        box.addWidget(self.scroll, 1)

        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(9)
        self.chips = {
            "tps": StatChip("生成速率 tok/s", self.pal),
            "ttft": StatChip("首 token 延迟", self.pal),
            "prompt": StatChip("提示处理 tok/s", self.pal),
            "ctx": StatChip("上下文占用", self.pal),
        }
        for chip in self.chips.values():
            self.stats_row.addWidget(chip, 1)
        box.addLayout(self.stats_row)

        input_card = Card(name="card", margin=10, spacing=8)
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("输入消息…  Enter 发送，Shift + Enter 换行")
        self.input_edit.setFixedHeight(74)
        self.input_edit.installEventFilter(self)
        input_card.vbox.addWidget(self.input_edit)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.hint_label = QLabel("")
        self.hint_label.setObjectName("faint")
        bottom.addWidget(self.hint_label, 1)
        self.api_btn = QPushButton("打开服务设置")
        self.api_btn.clicked.connect(self.request_open_service.emit)
        self.api_btn.setVisible(False)
        bottom.addWidget(self.api_btn)
        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primary")
        self.send_btn.setFixedWidth(92)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self.send_message)
        bottom.addWidget(self.send_btn)
        input_card.vbox.addLayout(bottom)
        box.addWidget(input_card)
        return page

    # ---------------- CLI 终端页 ----------------
    def _build_cli_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(11)

        self.terminal = QPlainTextEdit()
        self.terminal.setObjectName("terminal")
        self.terminal.setReadOnly(True)
        self.terminal.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        box.addWidget(self.terminal, 1)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.cli_rate = QLabel("生成速率 — tok/s")
        self.cli_rate.setObjectName("badgeTeal")
        bar.addWidget(self.cli_rate)
        self.cli_hint = QLabel("llama-cli 交互模式：输入内容写入进程标准输入")
        self.cli_hint.setObjectName("faint")
        bar.addWidget(self.cli_hint, 1)
        self.cli_clear = QPushButton("清屏")
        self.cli_clear.clicked.connect(self.terminal.clear)
        bar.addWidget(self.cli_clear)
        box.addLayout(bar)

        row = Card(name="card", margin=10, spacing=8)
        self.cli_input = QLineEdit()
        self.cli_input.setPlaceholderText("输入内容后回车，直接发送给 llama-cli…")
        self.cli_input.returnPressed.connect(self.send_cli)
        row.vbox.addWidget(self.cli_input)
        lower = QHBoxLayout()
        lower.addStretch(1)
        self.cli_start_btn = QPushButton("启动 CLI")
        self.cli_start_btn.setObjectName("primary")
        self.cli_start_btn.clicked.connect(self.request_start.emit)
        lower.addWidget(self.cli_start_btn)
        cli_send = QPushButton("发送")
        cli_send.setObjectName("primary")
        cli_send.setFixedWidth(92)
        cli_send.clicked.connect(self.send_cli)
        lower.addWidget(cli_send)
        row.vbox.addLayout(lower)
        box.addWidget(row)
        return page

    def eventFilter(self, obj, event) -> bool:
        if obj is self.input_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self.send_message()
                    return True
        return super().eventFilter(obj, event)

    # ---------------- 消息渲染 ----------------
    def _welcome(self) -> None:
        self._add_bubble(
            "assistant",
            "<b>Llama Studio</b><br><br>左侧可切换工作区：<br>"
            "&nbsp;&nbsp;• <b>对话</b> — 与本地模型交互（server 走 HTTP，cli 走终端）<br>"
            "&nbsp;&nbsp;• <b>服务</b> — 启动 llama-server 并把 API 提供给其他软件<br>"
            "&nbsp;&nbsp;• <b>模型</b> — 管理 .gguf 文件并切换当前模型<br><br>"
            "先在「服务」页启动服务，或在「模型」页选择模型后回来对话。",
        )

    def _add_bubble(self, role: str, html_text: str) -> MessageBubble:
        bubble = MessageBubble(role, self.pal)
        bubble.set_text(html_text)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        if role == "user":
            lay.addStretch(1)
            lay.addWidget(bubble, 7)
        else:
            lay.addWidget(bubble, 8)
            lay.addStretch(1)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, row)
        # 初次布局前 viewport 宽度尚未确定，延迟重算避免高度虚高
        QTimer.singleShot(0, bubble.fit_height)
        QTimer.singleShot(90, bubble.fit_height)
        QTimer.singleShot(20, self._scroll_bottom)
        return bubble

    def _scroll_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def new_session(self) -> None:
        if self.generating:
            self.stop_generation()
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.messages.clear()
        self.content_buffer = ""
        self.reasoning_buffer = ""
        self.current_bubble = None
        for chip in self.chips.values():
            chip.set_value("—")
        self._welcome()

    # ---------------- 发送 / 生成 ----------------
    def send_message(self) -> None:
        if self.mode != "llama-server":
            return
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        if self.generating:
            return
        if not self.ready:
            self.hint_label.setText("服务尚未就绪，请先启动 llama-server")
            self.request_open_service.emit()
            return
        self.input_edit.clear()
        self.hint_label.setText("")
        self._add_bubble("user", html.escape(text).replace("\n", "<br>"))
        self.messages.append({"role": "user", "content": text})
        self.current_bubble = self._add_bubble("assistant", "▍")
        self.content_buffer = ""
        self.reasoning_buffer = ""
        self.generating = True
        self.stop_btn.setVisible(True)
        self.send_btn.setEnabled(False)
        for chip in self.chips.values():
            chip.set_value("…")

        payload = []
        system = self.prompt_edit.toPlainText().strip()
        if system:
            payload.append({"role": "system", "content": system})
        payload += self.messages
        try:
            max_tokens = int(self.cfg.get("max_tokens") or 0) or None
        except ValueError:
            max_tokens = None
        try:
            temperature = float(self.cfg.get("temperature")) if self.cfg.get("temperature") else None
        except ValueError:
            temperature = None
        alias = str(self.cfg.get("alias") or "").strip() or "local-model"
        self.client.send(self.cfg.base_url(), str(self.cfg.get("api_key") or ""),
                         alias, payload, max_tokens, temperature)

    def _on_token(self, text: str) -> None:
        self.content_buffer += text
        self._refresh_timer.start()

    def _on_reasoning(self, text: str) -> None:
        self.reasoning_buffer += text
        self._refresh_timer.start()

    def _flush_buffer(self) -> None:
        if self.current_bubble is None:
            return
        thought = ""
        if self.reasoning_buffer:
            thought = (f'<div style="color:{self.pal.muted};font-size:12px;">'
                       f'<b>思考过程</b><br>{render_markdown(self.reasoning_buffer, self.pal)}'
                       f'</div><hr style="border:none;">')
        body = render_markdown(self.content_buffer, self.pal) if self.content_buffer else ""
        cursor = '<span style="color:%s;">▍</span>' % self.pal.accent if self.generating else ""
        self.current_bubble.set_text(thought + body + cursor)
        self._scroll_bottom()

    def stop_generation(self) -> None:
        if self.generating:
            self.client.cancel()

    def _on_done(self, ok: bool, message: str) -> None:
        self.generating = False
        self.stop_btn.setVisible(False)
        self.send_btn.setEnabled(True)
        self._flush_buffer()
        if self.content_buffer:
            self.messages.append({"role": "assistant", "content": self.content_buffer})
        if message and not ok:
            self.hint_label.setText(f"请求失败：{message}")
        elif message:
            self.hint_label.setText(message)
        self.content_buffer = ""
        self.reasoning_buffer = ""
        self.current_bubble = None

    def _on_stats(self, data: dict) -> None:
        def fmt(value, suffix="", digits=1):
            return "—" if value is None else f"{float(value):.{digits}f}{suffix}"

        self.chips["tps"].set_value(fmt(data.get("tps") or data.get("live_tps")))
        self.chips["ttft"].set_value(fmt(data.get("ttft_ms"), " ms", 0))
        self.chips["prompt"].set_value(fmt(data.get("prompt_tps")))
        ctx = data.get("ctx_used")
        cached = data.get("cached")
        self.chips["ctx"].set_value(
            "—" if ctx is None else f"{int(ctx)} tok" + (f" · 缓存 {int(cached)}" if cached else "")
        )

    # ---------------- CLI ----------------
    def send_cli(self) -> None:
        text = self.cli_input.text().strip()
        if not text:
            return
        if not self.proc.is_running():
            self.cli_hint.setText("llama-cli 未运行，请先点击「启动 CLI」")
            return
        ok, err = self.proc.send(text)
        if ok:
            self._append_terminal(f"> {text}\n")
            self.cli_input.clear()
            self.cli_hint.setText("已发送到 llama-cli 标准输入")
        else:
            self.cli_hint.setText(err)

    def _append_terminal(self, text: str) -> None:
        self.terminal.moveCursor(QTextCursor.MoveOperation.End)
        self.terminal.insertPlainText(strip_ansi(text))
        self.terminal.moveCursor(QTextCursor.MoveOperation.End)

    def _on_proc_output(self, text: str) -> None:
        if self.mode == "llama-cli":
            self._append_terminal(text)

    def _on_cli_perf(self, rate: float) -> None:
        if self.mode != "llama-cli":
            return
        self.cli_rate.setText(f"生成速率 {rate:.1f} tok/s")
        self.chips["tps"].set_value(f"{rate:.1f}")

    # ---------------- 状态联动 ----------------
    def set_mode(self, program_type: str, running: bool, ready: bool) -> None:
        self.mode = program_type
        self.running = running
        self.ready = ready
        is_cli = program_type == "llama-cli"
        self.stack.setCurrentIndex(1 if is_cli else 0)
        if is_cli:
            self.mode_badge.setObjectName("badgeTeal")
            self.mode_badge.setText("本地终端 · llama-cli")
            self.state_label.setText("运行中" if running else "未启动")
            self.cli_start_btn.setText("重启 CLI" if running else "启动 CLI")
        else:
            self.mode_badge.setObjectName("badge")
            self.mode_badge.setText("HTTP 对话 · llama-server")
            self.state_label.setText("服务就绪" if ready else ("加载中…" if running else "服务未启动"))
            self.hint_label.setText("" if ready else "服务未就绪，请在「服务」页启动 llama-server")
            self.api_btn.setVisible(not ready)
            self.send_btn.setEnabled(not self.generating)
        for label in (self.mode_badge,):
            label.style().unpolish(label)
            label.style().polish(label)
        self._apply_model_label()

    def _apply_model_label(self) -> None:
        model = str(self.cfg.get("model", "") or "")
        self.model_label.setText(("模型：" + model.split("\\")[-1].split("/")[-1]) if model else "未选择模型")

    def on_model_changed(self) -> None:
        self._apply_model_label()

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        for chip in self.chips.values():
            chip.set_palette(pal)
        for i in range(self.msg_layout.count() - 1):
            row = self.msg_layout.itemAt(i).widget()
            if row:
                for bubble in row.findChildren(MessageBubble):
                    bubble.set_palette(pal)
        if self.current_bubble:
            self._flush_buffer()
