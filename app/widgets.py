# -*- coding: utf-8 -*-
"""通用自绘控件：卡片、导航、开关、折叠面板、指标芯片、分段选择器等。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from .icons import draw_icon
from .theme import Palette


class Card(QFrame):
    def __init__(self, parent=None, name: str = "card", margin: int = 16, spacing: int = 11):
        super().__init__(parent)
        self.setObjectName(name)
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(margin, margin - 2, margin, margin - 2)
        self.vbox.setSpacing(spacing)


class SoftCard(Card):
    def __init__(self, parent=None, name: str = "softcard", margin: int = 14):
        super().__init__(parent, name, margin)


class NavButton(QPushButton):
    def __init__(self, kind: str, text: str, pal: Palette, parent=None):
        super().__init__(text, parent)
        self.kind = kind
        self.pal = pal
        self.active = False
        self.setObjectName("quiet")
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self.update()

    def set_active(self, value: bool) -> None:
        self.active = value
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        if self.active:
            painter.setBrush(QColor(self.pal.accent_soft))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 11, 11)
            painter.setBrush(QColor(self.pal.accent))
            painter.drawRoundedRect(QRectF(2, 11, 3, 20), 1.5, 1.5)
        elif self.underMouse():
            painter.setBrush(QColor(self.pal.surface2))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 11, 11)
        color = self.pal.accent if self.active else self.pal.muted
        draw_icon(painter, QRectF(15, 9, 24, 24), self.kind, color)
        painter.setPen(QColor(self.pal.accent if self.active else self.pal.text))
        font = painter.font()
        font.setPointSize(10)
        font.setWeight(QFont.Weight.DemiBold if self.active else QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(QRectF(48, 0, self.width() - 54, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())


class ToggleSwitch(QAbstractButton):
    def __init__(self, pal: Palette, parent=None, checked: bool = False):
        super().__init__(parent)
        self.pal = pal
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(38, 21)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        on = self.isChecked()
        track = QColor(self.pal.accent if on else self.pal.border_strong)
        if not on:
            track.setAlpha(170)
        painter.setBrush(track)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(0, 1, 38, 19), 9.5, 9.5)
        knob = QColor(self.pal.on_accent if on else self.pal.surface)
        painter.setBrush(knob)
        x = 19.0 if on else 2.0
        painter.drawEllipse(QRectF(x, 3.5, 14, 14))

    def mousePressEvent(self, event) -> None:
        self.setChecked(not self.isChecked())
        event.accept()


class Collapsible(QWidget):
    toggled = Signal(bool)

    def __init__(self, title: str, pal: Palette, parent=None, subtitle: str = ""):
        super().__init__(parent)
        self.pal = pal
        self._open = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 0, 0)
        head.setSpacing(8)
        self.arrow = QPushButton()
        self.arrow.setObjectName("quiet")
        self.arrow.setFixedSize(22, 22)
        self.arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        self.arrow.clicked.connect(self.toggle)
        head.addWidget(self.arrow)

        label = QLabel(title)
        label.setObjectName("h2")
        head.addWidget(label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("faint")
            head.addWidget(sub)
        head.addStretch(1)
        root.addLayout(head)

        self.content = QWidget()
        self.content.setVisible(False)
        self.vbox = QVBoxLayout(self.content)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(10)
        root.addWidget(self.content)
        self._refresh_arrow()

    def _refresh_arrow(self) -> None:
        self.arrow.setIcon(_icon_pixmap("chevron_down" if self._open else "chevron_right", self.pal.muted))
        self.arrow.setIconSize(QSize(18, 18))

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self._refresh_arrow()

    def toggle(self) -> None:
        self._open = not self._open
        self.content.setVisible(self._open)
        self._refresh_arrow()
        self.toggled.emit(self._open)

    def set_open(self, value: bool) -> None:
        if value != self._open:
            self.toggle()


def _icon_pixmap(kind: str, color: str):
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap(QSize(22, 22))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    draw_icon(painter, QRectF(2, 2, 18, 18), kind, color)
    painter.end()
    return QIcon(pm)


class StatChip(QFrame):
    def __init__(self, label: str, pal: Palette, parent=None):
        super().__init__(parent)
        self.pal = pal
        self.setObjectName("softcard")
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(2)
        self.label = QLabel(label)
        self.label.setObjectName("muted")
        self.value = QLabel("—")
        self.value.setObjectName("h2")
        self.value.setStyleSheet(f"color: {pal.accent};")
        box.addWidget(self.label)
        box.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(text)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self.value.setStyleSheet(f"color: {pal.accent};")


class Segmented(QWidget):
    changed = Signal(str)

    def __init__(self, options: list[str], pal: Palette, parent=None):
        super().__init__(parent)
        self.pal = pal
        self.options = options
        self.current = options[0]
        box = QHBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(2)
        shell = QFrame()
        shell.setObjectName("softcard")
        lay = QHBoxLayout(shell)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.buttons: dict[str, QPushButton] = {}
        for text in options:
            btn = QPushButton(text)
            btn.setObjectName("segment")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, t=text: self.select(t))
            lay.addWidget(btn)
            self.buttons[text] = btn
        box.addWidget(shell)
        box.addStretch(1)
        self._refresh()

    def _refresh(self) -> None:
        for text, btn in self.buttons.items():
            active = text == self.current
            btn.setProperty("active", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def select(self, text: str) -> None:
        if text == self.current:
            return
        self.current = text
        self._refresh()
        self.changed.emit(text)


class PathRow(QWidget):
    path_changed = Signal(str)

    def __init__(self, pal: Palette, mode: str = "file", file_filter: str = "所有文件 (*)", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.file_filter = file_filter
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("选择路径…")
        self.edit.editingFinished.connect(lambda: self.path_changed.emit(self.edit.text()))
        box.addWidget(self.edit, 1)
        btn = QPushButton("浏览")
        btn.setFixedWidth(62)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._browse)
        box.addWidget(btn)

    def _browse(self) -> None:
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "选择目录", self.edit.text())
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", self.edit.text(), self.file_filter)
        if path:
            self.edit.setText(path)
            self.path_changed.emit(path)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, value: str) -> None:
        self.edit.setText(value)


class TipBar(QFrame):
    action_clicked = Signal()

    def __init__(self, pal: Palette, parent=None):
        super().__init__(parent)
        self.setObjectName("tealcard")
        self.setVisible(False)
        box = QHBoxLayout(self)
        box.setContentsMargins(14, 9, 12, 9)
        box.setSpacing(10)
        self.label = QLabel("")
        box.addWidget(self.label, 1)
        self.action = QPushButton("重启并应用")
        self.action.setObjectName("primary")
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.clicked.connect(self.action_clicked.emit)
        box.addWidget(self.action)
        self.close_btn = QPushButton("忽略")
        self.close_btn.setObjectName("quiet")
        self.close_btn.clicked.connect(lambda: self.setVisible(False))
        box.addWidget(self.close_btn)

    def show_message(self, text: str, action: str = "重启并应用") -> None:
        self.label.setText(text)
        self.action.setText(action)
        self.setVisible(True)


class SectionHeader(QWidget):
    def __init__(self, title: str, pal: Palette, parent=None, right: QWidget | None = None):
        super().__init__(parent)
        box = QHBoxLayout(self)
        box.setContentsMargins(2, 2, 2, 2)
        box.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("h1")
        box.addWidget(label)
        box.addStretch(1)
        if right is not None:
            box.addWidget(right)
