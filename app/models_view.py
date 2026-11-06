# -*- coding: utf-8 -*-
"""模型视图：扫描 .gguf、展示元信息、切换当前模型并提示重启服务。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .config import Config, ModelInfo
from .icons import draw_icon
from .theme import Palette
from .widgets import Card, PathRow, SectionHeader, TipBar


class ModelCard(Card):
    clicked = Signal(str)

    def __init__(self, info: ModelInfo, pal: Palette, active: bool, parent=None):
        super().__init__(parent, "card", margin=14, spacing=7)
        self.info = info
        self.pal = pal
        self.active = active
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(94)
        self._apply_style()

        row = QHBoxLayout()
        row.setSpacing(12)
        self.icon = QWidget()
        self.icon.setFixedSize(38, 38)
        row.addWidget(self.icon)

        info_box = QVBoxLayout()
        info_box.setSpacing(3)
        name = QLabel(info.name)
        name.setObjectName("h2")
        info_box.addWidget(name)
        meta = QLabel(f"{info.size_text}   ·   {info.quant}   ·   {info.modified}")
        meta.setObjectName("faint")
        info_box.addWidget(meta)
        path = QLabel(info.path_text)
        path.setObjectName("faint")
        path.setStyleSheet(f"color: {pal.faint};")
        info_box.addWidget(path)
        row.addLayout(info_box, 1)

        self.tag = QLabel("当前使用" if active else "设为当前")
        self.tag.setObjectName("badgeTeal" if active else "faint")
        self.tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tag.setFixedWidth(76)
        row.addWidget(self.tag)
        self.vbox.addLayout(row)

    def _apply_style(self) -> None:
        if self.active:
            self.setStyleSheet(
                f"QFrame#card {{ background: {self.pal.teal_soft}; border: 1px solid {self.pal.teal}; border-radius: 14px; }}"
            )
        else:
            self.setStyleSheet("")

    def set_active(self, value: bool) -> None:
        self.active = value
        self.tag.setText("当前使用" if value else "设为当前")
        self.tag.setObjectName("badgeTeal" if value else "faint")
        self.tag.style().unpolish(self.tag)
        self.tag.style().polish(self.tag)
        self._apply_style()
        self.update()

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self._apply_style()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.icon.geometry())
        painter.setBrush(self.pal.teal_soft)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 11, 11)
        draw_icon(painter, rect.adjusted(8, 8, -8, -8), "cube", self.pal.teal)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.info.path_text)
        super().mousePressEvent(event)


class ModelsView(QWidget):
    model_changed = Signal(str)
    restart_requested = Signal()

    def __init__(self, cfg: Config, pal: Palette, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.pal = pal
        self.cards: list[ModelCard] = []
        self.current = str(cfg.get("model", "") or "")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 14, 20, 18)
        outer.setSpacing(13)

        self.head = SectionHeader("模型", pal)
        self.count_label = QLabel("")
        self.count_label.setObjectName("faint")
        self.head.layout().addWidget(self.count_label)
        outer.addWidget(self.head)

        scan_card = Card()
        row = QHBoxLayout()
        row.setSpacing(10)
        lab = QLabel("扫描目录")
        lab.setObjectName("muted")
        lab.setFixedWidth(70)
        row.addWidget(lab)
        self.scan_row = PathRow(self.pal, "dir")
        self.scan_row.path_changed.connect(self._on_scan_dir)
        row.addWidget(self.scan_row, 1)
        self.rescan_btn = QPushButton("重新扫描")
        self.rescan_btn.setObjectName("primary")
        self.rescan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rescan_btn.clicked.connect(self.scan)
        row.addWidget(self.rescan_btn)
        scan_card.vbox.addLayout(row)
        tip = QLabel("递归扫描目录下的 .gguf 文件；点击卡片即可设为当前模型。")
        tip.setObjectName("faint")
        scan_card.vbox.addWidget(tip)
        outer.addWidget(scan_card)

        self.tip = TipBar(pal)
        self.tip.action_clicked.connect(self._on_restart)
        outer.addWidget(self.tip)

        self.current_card = Card(name="tealcard", margin=15)
        cl = QHBoxLayout()
        cl.setSpacing(10)
        self.current_name = QLabel("未选择模型")
        self.current_name.setObjectName("h1")
        cl.addWidget(self.current_name, 1)
        self.current_meta = QLabel("")
        self.current_meta.setObjectName("muted")
        cl.addWidget(self.current_meta)
        self.current_card.vbox.addLayout(cl)
        self.current_path = QLabel("请在下方列表中选择一个模型")
        self.current_path.setObjectName("faint")
        self.current_card.vbox.addWidget(self.current_path)
        outer.addWidget(self.current_card)

        list_head = QHBoxLayout()
        lt = QLabel("可用模型")
        lt.setObjectName("h2")
        list_head.addWidget(lt)
        list_head.addStretch(1)
        outer.addLayout(list_head)

        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setFrameShape(QFrame.Shape.NoFrame)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_box = QVBoxLayout(self.list_host)
        self.list_box.setContentsMargins(2, 2, 6, 2)
        self.list_box.setSpacing(10)
        self.scroller.setWidget(self.list_host)
        outer.addWidget(self.scroller, 1)

        self.scan_row.set_text(str(cfg.get("scan_dir", "") or ""))
        self.scan()

    def _on_scan_dir(self, value: str) -> None:
        self.cfg.set("scan_dir", value)
        self.scan()

    def _on_restart(self) -> None:
        self.tip.setVisible(False)
        self.restart_requested.emit()

    def scan(self) -> None:
        infos = self.cfg.scan_models()
        while self.list_box.count():
            item = self.list_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards.clear()
        self.count_label.setText(f"共 {len(infos)} 个 .gguf 文件")
        current = str(self.cfg.get("model", "") or "")
        for info in infos:
            active = info.path_text.replace("\\", "/").lower() == current.replace("\\", "/").lower()
            card = ModelCard(info, self.pal, active)
            card.clicked.connect(self.select)
            self.list_box.addWidget(card)
            self.cards.append(card)
        if not infos:
            empty = QLabel("未找到 .gguf 模型。请先设置扫描目录，或点击「重新扫描」。")
            empty.setObjectName("muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_box.addWidget(empty)
        self.list_box.addStretch(1)
        self._refresh_current()

    def _refresh_current(self) -> None:
        current = str(self.cfg.get("model", "") or "")
        self.current = current
        match = next((c for c in self.cards if c.info.path_text == current), None)
        if match:
            self.current_name.setText(match.info.name)
            self.current_meta.setText(f"{match.info.size_text}  ·  {match.info.quant}")
            self.current_path.setText(match.info.path_text)
        elif current:
            self.current_name.setText(current.replace("\\", "/").split("/")[-1])
            self.current_meta.setText("自定义路径")
            self.current_path.setText(current)
        else:
            self.current_name.setText("未选择模型")
            self.current_meta.setText("")
            self.current_path.setText("请在下方列表中选择一个模型")
        for card in self.cards:
            card.set_active(card.info.path_text == current)

    def select(self, path: str, notify: bool = True) -> None:
        old = str(self.cfg.get("model", "") or "")
        self.cfg.set("model", path)
        self._refresh_current()
        self.model_changed.emit(path)
        if notify and old != path:
            name = path.replace("\\", "/").split("/")[-1]
            self.tip.show_message(f"已切换为 {name}，需重启运行中的程序后才会生效。")

    def sync_dir(self) -> None:
        """服务页重新指定 llama.cpp 目录后，同步扫描目录与模型列表。"""
        self.scan_row.blockSignals(True)
        self.scan_row.set_text(str(self.cfg.get("scan_dir", "") or ""))
        self.scan_row.blockSignals(False)
        self.scan()

    def refresh_from_config(self) -> None:
        self._refresh_current()

    def set_running(self, running: bool) -> None:
        self.tip.setVisible(self.tip.isVisible() and running)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        for card in self.cards:
            card.set_palette(pal)
