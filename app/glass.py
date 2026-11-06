# -*- coding: utf-8 -*-
"""无边框圆角窗口、Windows 原生毛玻璃（Mica / Acrylic）与自绘标题栏。

Qt 的 WA_TranslucentBackground 只能掏空背景，不会产生模糊；真正的磨砂由 DWM
合成器完成。这里同时做两件事：
  1. 调用 DWM 让窗口背后的内容被系统模糊；
  2. 用 QPainter 画一层半透明着色 + 高光边 + 阴影，即使 DWM 不可用也保持观感。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor, QIcon, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QVBoxLayout, QWidget,
)

from .icons import draw_icon
from .theme import Palette

IS_WIN = sys.platform == "win32"


def win_build() -> int:
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WindowCompositionAttributeData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def enable_glass(hwnd: int, dark: bool, enabled: bool = True) -> str:
    """返回实际生效的模式描述，供状态提示使用。"""
    if not IS_WIN:
        return "自绘磨砂（非 Windows）"
    if not enabled:
        try:
            accent = _AccentPolicy(0, 0, 0, 0)
            data = _WindowCompositionAttributeData(
                19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent)
            )
            api = ctypes.windll.user32.SetWindowCompositionAttribute
            api.argtypes = [wintypes.HWND, ctypes.c_void_p]
            api.restype = wintypes.BOOL
            api(wintypes.HWND(hwnd), ctypes.byref(data))
        except Exception:
            pass
        return "自绘磨砂"
    build = win_build()
    # Win11：系统级 backdrop（Acrylic = 3，Mica = 2）与圆角策略
    if build >= 22000:
        try:
            dwm = ctypes.windll.dwmapi
            fn = dwm.DwmSetWindowAttribute
            # 64 位下必须显式声明 argtypes，否则 HWND 会被截断为 32 位整数
            fn.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            fn.restype = ctypes.c_long
            backdrop = ctypes.c_int(3)
            fn(wintypes.HWND(hwnd), 38, ctypes.byref(backdrop), 4)
            corner = ctypes.c_int(2)
            fn(wintypes.HWND(hwnd), 33, ctypes.byref(corner), 4)
            dark_mode = ctypes.c_int(1 if dark else 0)
            fn(wintypes.HWND(hwnd), 20, ctypes.byref(dark_mode), 4)
        except Exception:
            pass
    # Win10（及 Win11 兜底）：未公开的 SetWindowCompositionAttribute / Acrylic
    try:
        tint = 0xB0202020 if dark else 0xB8FFFFFF  # ABGR
        accent = _AccentPolicy(4, 2, tint, 0)
        data = _WindowCompositionAttributeData(
            19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent)
        )
        api = ctypes.windll.user32.SetWindowCompositionAttribute
        api.argtypes = [wintypes.HWND, ctypes.c_void_p]
        api.restype = wintypes.BOOL
        ok = api(wintypes.HWND(hwnd), ctypes.byref(data))
        if ok:
            return "Acrylic 毛玻璃"
    except Exception:
        pass
    return "Mica 毛玻璃" if build >= 22000 else "自绘磨砂"


class GlassSurface(QWidget):
    """窗口最外层：负责阴影、圆角、半透明着色与边缘缩放。"""

    PAD = 6
    RADIUS = 16

    def __init__(self, window: "FramelessWindow", pal: Palette):
        super().__init__(window)
        self._win = window
        self.pal = pal
        self.maximized = False
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self.update()

    def _body_rect(self) -> QRectF:
        m = 0 if self.maximized else self.PAD
        return QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

    def _rounded(self, rect: QRectF, radius: float) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self._body_rect()
        radius = 0 if self.maximized else self.RADIUS

        # 极淡的三层柔光：只提供层次，不再在窗口外围形成一圈清晰矩形轮廓
        if not self.maximized:
            for i in range(3, 0, -1):
                c = QColor(self.pal.shadow)
                c.setAlpha(max(2, int(self.pal.shadow.alpha() * (4 - i) / 30)))
                outer = r.adjusted(-i, -i, i, i)
                painter.fillPath(self._rounded(outer, radius + i), c)

        top = QColor(self.pal.glass)
        bottom = QColor(self.pal.glass)
        top.setAlpha(min(255, top.alpha() + 12))
        bottom.setAlpha(max(150, bottom.alpha() - 14))
        grad = QLinearGradient(QPointF(r.left(), r.top()), QPointF(r.right(), r.bottom()))
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bottom)
        painter.fillPath(self._rounded(r, radius), grad)

        # 不再绘制最外圈描边：窗口边界仅由圆角着色与柔和阴影表达
        if not self.maximized:
            painter.setPen(QPen(QColor(self.pal.scroll), 1.2))
            bx, by = r.right() - 14, r.bottom() - 14
            for k in (0, 4, 8):
                painter.drawLine(QPointF(bx - k, by), QPointF(bx, by - k))

    def _edges(self, pos) -> Qt.Edges:
        if self.maximized:
            return Qt.Edges()
        m = 7
        x, y = pos.x(), pos.y()
        edges = Qt.Edges()
        if x <= m:
            edges |= Qt.Edge.LeftEdge
        if x >= self.width() - m:
            edges |= Qt.Edge.RightEdge
        if y <= m:
            edges |= Qt.Edge.TopEdge
        if y >= self.height() - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        edges = self._edges(event.position().toPoint())
        if edges == Qt.Edges():
            self.unsetCursor()
        elif edges & Qt.Edge.LeftEdge and edges & Qt.Edge.TopEdge or edges & Qt.Edge.RightEdge and edges & Qt.Edge.BottomEdge:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges & Qt.Edge.RightEdge and edges & Qt.Edge.TopEdge or edges & Qt.Edge.LeftEdge and edges & Qt.Edge.BottomEdge:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeVerCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        edges = self._edges(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and edges != Qt.Edges():
            handle = self._win.windowHandle()
            if handle is not None:
                handle.startSystemResize(edges)
                return
        super().mousePressEvent(event)


class IconButton(QPushButton):
    def __init__(self, kind: str, parent: QWidget, pal: Palette, size: int = 30, tooltip: str = ""):
        super().__init__(parent)
        self.kind = kind
        self.pal = pal
        self.icon_color = pal.muted
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("quiet")
        self.setToolTip(tooltip)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self.icon_color = pal.muted
        self.update()

    def set_icon(self, kind: str, color: str | None = None) -> None:
        self.kind = kind
        if color:
            self.icon_color = color
        self.update()

    def paintEvent(self, _event) -> None:
        super().paintEvent(_event)
        painter = QPainter(self)
        draw_icon(painter, QRectF(5, 5, self.width() - 10, self.height() - 10), self.kind, self.icon_color)


class TitleBar(QWidget):
    theme_toggled = Signal()
    glass_toggled = Signal()

    def __init__(self, window: "FramelessWindow", title: str, pal: Palette):
        super().__init__(window)
        self._win = window
        self.pal = pal
        self.setFixedHeight(48)
        self.setObjectName("titlebar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 8, 4)
        layout.setSpacing(8)

        self.logo = QWidget(self)
        self.logo.setFixedSize(26, 26)
        layout.addWidget(self.logo)
        icon_file = Path(__file__).resolve().parent.parent / "assets" / "app.ico"
        self.logo_icon = QIcon(str(icon_file)) if icon_file.is_file() else None

        name = QLabel(title)
        name.setObjectName("h2")
        layout.addWidget(name)
        ver = QLabel("v0.0.3")
        ver.setObjectName("faint")
        layout.addSpacing(4)
        layout.addWidget(ver)

        layout.addSpacing(16)
        self.center_layout = QHBoxLayout()
        self.center_layout.setSpacing(8)
        layout.addLayout(self.center_layout, 1)

        self.glass_btn = IconButton("sparkle", self, pal, 30, "切换毛玻璃效果")
        self.glass_btn.clicked.connect(self.glass_toggled.emit)
        self.theme_btn = IconButton("moon" if pal.name == "light" else "sun", self, pal, 30, "切换浅色 / 深色主题")
        self.theme_btn.clicked.connect(self.theme_toggled.emit)
        layout.addWidget(self.glass_btn)
        layout.addWidget(self.theme_btn)

        layout.addSpacing(6)
        self.min_btn = IconButton("minimize", self, pal, 28, "最小化")
        self.max_btn = IconButton("maximize", self, pal, 28, "最大化 / 还原")
        self.close_btn = IconButton("close", self, pal, 28, "关闭")
        self.min_btn.clicked.connect(self._win.showMinimized)
        self.max_btn.clicked.connect(self._win.toggle_maximize)
        self.close_btn.clicked.connect(self._win.close)
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        for btn in (self.glass_btn, self.theme_btn, self.min_btn, self.max_btn, self.close_btn):
            btn.set_palette(pal)
        self.theme_btn.set_icon("moon" if pal.name == "light" else "sun")
        self.update()

    def paintEvent(self, _event) -> None:
        super().paintEvent(_event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.logo.geometry())
        if self.logo_icon is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            self.logo_icon.paint(painter, rect.toRect())
        else:
            painter.setBrush(QColor(self.pal.accent))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 8, 8)
            draw_icon(painter, rect.adjusted(4, 4, -4, -4), "bolt", self.pal.on_accent, 2.0)

    def _interactive_child(self, pos) -> bool:
        child = self.childAt(pos)
        while child is not None and child is not self:
            if isinstance(child, (QPushButton, QComboBox, QLineEdit)):
                return True
            child = child.parentWidget()
        return False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._interactive_child(event.position().toPoint()):
            handle = self._win.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self._interactive_child(event.position().toPoint()):
            self._win.toggle_maximize()
            return
        super().mouseDoubleClickEvent(event)


class FramelessWindow(QMainWindow):
    glass_mode_changed = Signal(str)

    def __init__(self, pal: Palette, title: str):
        super().__init__()
        self.pal = pal
        self.glass_enabled = True
        self._maximized = False
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1180, 760)
        self.setMinimumSize(920, 620)

        self.surface = GlassSurface(self, pal)
        self.setCentralWidget(self.surface)
        outer = QVBoxLayout(self.surface)
        outer.setContentsMargins(GlassSurface.PAD, GlassSurface.PAD, GlassSurface.PAD, GlassSurface.PAD)
        outer.setSpacing(0)

        self.title_bar = TitleBar(self, title, pal)
        self.title_bar.theme_toggled.connect(self._on_theme_toggle)
        self.title_bar.glass_toggled.connect(self.toggle_glass)
        outer.addWidget(self.title_bar)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        outer.addWidget(self.body, 1)

    def _on_theme_toggle(self) -> None:
        # 由主窗口覆写具体行为；此处仅保证信号存在
        pass

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self.surface.set_palette(pal)
        self.title_bar.set_palette(pal)
        self.apply_glass()

    def toggle_maximize(self) -> None:
        if self._maximized:
            self.showNormal()
            self._maximized = False
        else:
            self.showMaximized()
            self._maximized = True
        self.surface.maximized = self._maximized
        layout = self.surface.layout()
        if layout is not None:
            m = 0 if self._maximized else GlassSurface.PAD
            layout.setContentsMargins(m, m, m, m)
        self.surface.update()

    def toggle_glass(self) -> None:
        self.glass_enabled = not self.glass_enabled
        self.apply_glass()

    def apply_glass(self) -> None:
        try:
            mode = enable_glass(int(self.winId()), self.pal.name == "dark", self.glass_enabled)
        except Exception as exc:
            mode = f"自绘磨砂（{type(exc).__name__}）"
        self.glass_mode_changed.emit(mode)
        self.surface.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.apply_glass()
