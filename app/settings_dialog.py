# -*- coding: utf-8 -*-
"""右上角「设置」打开的外观设置对话框（非模态，改动即时预览并持久化）。

可设置：浅/深主题、强调色、窗口背景色、面板背景色、用户气泡色、
背景图片、背景不透明度、界面字号、毛玻璃效果开关。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QLabel, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from .config import Config, base_dir
from .theme import DEFAULT_APPEARANCE, Palette

PRESETS = ["#5B5BD6", "#2F6FED", "#0E8A6B", "#D97706", "#C2415B", "#7C3AED", "#334155"]


class AppearanceDialog(QDialog):
    appearance_changed = Signal(dict)

    def __init__(self, cfg: Config, pal: Palette, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.pal = pal
        self._updating = False
        saved = cfg.get("appearance") or {}
        self.state: dict = {**DEFAULT_APPEARANCE, **{
            k: v for k, v in saved.items() if k in DEFAULT_APPEARANCE}}
        self.state["theme"] = str(cfg.get("theme") or "light")
        self.state["glass"] = bool(cfg.get("glass", True))

        self.setWindowTitle("外观设置")
        self.setModal(False)
        self.setMinimumWidth(430)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowCloseButtonHint)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(9)

        title = QLabel("外观设置")
        title.setObjectName("h1")
        root.addWidget(title)
        hint = QLabel("所有改动即时生效并自动保存；「恢复默认」回到原始配色。")
        hint.setObjectName("faint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # 主题 + 毛玻璃
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("主题"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.setCurrentIndex(1 if self.state["theme"] == "dark" else 0)
        self.theme_combo.currentIndexChanged.connect(self._on_theme)
        row.addWidget(self.theme_combo, 1)
        self.glass_box = QCheckBox("毛玻璃效果")
        self.glass_box.setChecked(self.state["glass"])
        self.glass_box.toggled.connect(self._on_glass)
        row.addWidget(self.glass_box)
        root.addLayout(row)

        # 背景不透明度
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("背景不透明度"))
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(120, 255)
        self.alpha_slider.setValue(int(self.state.get("glass_alpha") or 214)
                                   if self.state.get("glass_alpha") else 214)
        self.alpha_slider.valueChanged.connect(self._on_alpha)
        row.addWidget(self.alpha_slider, 1)
        self.alpha_label = QLabel("")
        self.alpha_label.setFixedWidth(38)
        row.addWidget(self.alpha_label)
        root.addLayout(row)

        # 字号
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("界面字号"))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(11, 18)
        self.font_spin.setValue(int(self.state.get("font_size") or 13))
        self.font_spin.valueChanged.connect(self._on_font)
        row.addWidget(self.font_spin)
        row.addStretch(1)
        root.addLayout(row)

        root.addWidget(self._separator("颜色"))

        # 强调色预设 + 自定义
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel("强调色"))
        row.addStretch(1)
        self.preset_buttons: list[QPushButton] = []
        for color in PRESETS:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(color)
            btn.clicked.connect(lambda _=False, c=color: self._set_color("accent", c))
            self.preset_buttons.append(btn)
            row.addWidget(btn)
        root.addLayout(row)

        self.color_rows: dict[str, QPushButton] = {}
        for key, label, fallback in (
            ("accent", "自定义强调色", "#5B5BD6"),
            ("background", "窗口背景色", "#FFFFFF"),
            ("panel", "面板 / 卡片背景", "#F5F7FC"),
            ("bubble", "用户气泡颜色", "#E9EDFF"),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            cap = QLabel(label)
            cap.setMinimumWidth(112)
            row.addWidget(cap)
            btn = QPushButton("选择颜色…")
            btn.setObjectName("mini")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key, f=fallback: self._pick_color(k, f))
            self.color_rows[key] = btn
            row.addWidget(btn, 1)
            clear = QPushButton("清除")
            clear.setObjectName("quiet")
            clear.setFixedWidth(48)
            clear.clicked.connect(lambda _=False, k=key: self._set_color(k, ""))
            row.addWidget(clear)
            root.addLayout(row)

        root.addWidget(self._separator("背景图片"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.image_label = QLabel("无")
        self.image_label.setObjectName("faint")
        self.image_label.setMinimumWidth(150)
        row.addWidget(self.image_label, 1)
        pick = QPushButton("选择图片…")
        pick.setObjectName("mini")
        pick.clicked.connect(self._pick_image)
        row.addWidget(pick)
        clear_img = QPushButton("清除")
        clear_img.setObjectName("quiet")
        clear_img.clicked.connect(lambda: self._set_image(""))
        row.addWidget(clear_img)
        root.addLayout(row)

        row = QHBoxLayout()
        row.addStretch(1)
        reset = QPushButton("恢复默认")
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        close = QPushButton("关闭")
        close.setObjectName("primary")
        close.clicked.connect(self.close)
        row.addWidget(close)
        root.addLayout(row)

        self._refresh()

    # ---------------- 控件 ----------------
    def _separator(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("h2")
        lab.setStyleSheet("margin-top: 4px;")
        return lab

    def _refresh(self) -> None:
        self._updating = True
        try:
            alpha = int(self.state.get("glass_alpha") or 214)
            self.alpha_label.setText(f"{alpha}")
            self.alpha_slider.setValue(alpha)
            color = self.state.get("accent") or ""
            for btn, preset in zip(self.preset_buttons, PRESETS):
                active = color.lower() == preset.lower()
                border = "2px solid " + (self.pal.text if active else "transparent")
                btn.setStyleSheet(
                    f"QPushButton {{ background: {preset}; border: {border};"
                    f" border-radius: 6px; }}")
            for key, btn in self.color_rows.items():
                value = self.state.get(key) or ""
                btn.setText(value if value else "选择颜色…")
                p = self.pal
                if value:
                    btn.setStyleSheet(
                        f"QPushButton {{ background: {p.surface2}; color: {p.text};"
                        f" border: 1px solid {p.border}; border-left: 12px solid {value};"
                        f" border-radius: 8px; padding: 5px 8px; }}")
                else:
                    btn.setStyleSheet("")
            image = str(self.state.get("bg_image") or "")
            self.image_label.setText(Path(image).name if image else "无")
        finally:
            self._updating = False

    def _emit(self) -> None:
        self._refresh()
        if not self._updating:
            self.appearance_changed.emit(dict(self.state))

    def _set_color(self, key: str, value: str) -> None:
        self.state[key] = value
        self._emit()

    def _pick_color(self, key: str, fallback: str) -> None:
        initial = QColor(self.state.get(key) or fallback)
        color = QColorDialog.getColor(initial, self, "选择颜色")
        if color.isValid():
            self._set_color(key, color.name())

    def _set_image(self, value: str) -> None:
        self.state["bg_image"] = value
        self._emit()

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        src = Path(path)
        assets = base_dir() / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        for old in assets.glob("background.*"):
            try:
                old.unlink()
            except OSError:
                pass
        target = assets / ("background" + src.suffix.lower())
        shutil.copyfile(str(src), str(target))
        self._set_image(f"assets/{target.name}")

    # ---------------- 事件 ----------------
    def _on_theme(self, index: int) -> None:
        if self._updating:
            return
        self.state["theme"] = self.theme_combo.itemData(index)
        self._emit()

    def _on_glass(self, value: bool) -> None:
        if self._updating:
            return
        self.state["glass"] = bool(value)
        self._emit()

    def _on_alpha(self, value: int) -> None:
        if self._updating:
            return
        self.state["glass_alpha"] = int(value)
        self._emit()

    def _on_font(self, value: int) -> None:
        if self._updating:
            return
        self.state["font_size"] = int(value)
        self._emit()

    def _reset(self) -> None:
        self.state = {**DEFAULT_APPEARANCE, "theme": "light", "glass": True}
        assets = base_dir() / "assets"
        for old in assets.glob("background.*"):
            try:
                old.unlink()
            except OSError:
                pass
        self._updating = True
        self.theme_combo.setCurrentIndex(0)
        self.glass_box.setChecked(True)
        self.font_spin.setValue(13)
        self._updating = False
        self._emit()

    def sync_from_config(self) -> None:
        """主题按钮或毛玻璃按钮在别处被切换后，重新同步对话框状态。"""
        saved = self.cfg.get("appearance") or {}
        self.state = {**DEFAULT_APPEARANCE, **{
            k: v for k, v in saved.items() if k in DEFAULT_APPEARANCE}}
        self.state["theme"] = str(self.cfg.get("theme") or "light")
        self.state["glass"] = bool(self.cfg.get("glass", True))
        self._updating = True
        self.theme_combo.setCurrentIndex(1 if self.state["theme"] == "dark" else 0)
        self.glass_box.setChecked(self.state["glass"])
        self.font_spin.setValue(int(self.state.get("font_size") or 13))
        self._updating = False
        self._refresh()

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self._refresh()
