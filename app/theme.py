# -*- coding: utf-8 -*-
"""双主题调色板与全局 QSS。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    name: str
    surface: str
    surface2: str
    surface3: str
    border: str
    border_strong: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_hover: str
    accent_soft: str
    on_accent: str
    teal: str
    teal_soft: str
    user_bubble: str
    code_bg: str
    code_text: str
    success: str
    danger: str
    warn: str
    scroll: str
    shadow: QColor
    glass: QColor
    glass_edge: QColor


LIGHT = Palette(
    name="light",
    surface="#FFFFFF",
    surface2="#F5F7FC",
    surface3="#EDF0F8",
    border="#E3E7F1",
    border_strong="#CCD3E4",
    text="#1D2334",
    muted="#6C7590",
    faint="#9BA4BA",
    accent="#5B5BD6",
    accent_hover="#4B4BC4",
    accent_soft="#EEEDFE",
    on_accent="#FFFFFF",
    teal="#0E8A6B",
    teal_soft="#E3F4EE",
    user_bubble="#E9EDFF",
    code_bg="#F1F3FA",
    code_text="#2C3550",
    success="#16A34A",
    danger="#D64545",
    warn="#D98A0B",
    scroll="#C9D0E0",
    shadow=QColor(30, 38, 70, 46),
    glass=QColor(255, 255, 255, 214),
    glass_edge=QColor(255, 255, 255, 235),
)

DARK = Palette(
    name="dark",
    surface="#272C3B",
    surface2="#202534",
    surface3="#2F3548",
    border="#3A4257",
    border_strong="#4C5570",
    text="#ECEFF8",
    muted="#9DA6BD",
    faint="#78829B",
    accent="#9292FF",
    accent_hover="#A6A6FF",
    accent_soft="#33315C",
    on_accent="#141726",
    teal="#4ACFA8",
    teal_soft="#213638",
    user_bubble="#343B5C",
    code_bg="#191D2B",
    code_text="#D7DDF0",
    success="#3ECF7E",
    danger="#F07373",
    warn="#E7A94A",
    scroll="#4A536B",
    shadow=QColor(0, 0, 0, 120),
    glass=QColor(30, 34, 47, 216),
    glass_edge=QColor(255, 255, 255, 40),
)


def palette(name: str) -> Palette:
    return DARK if name == "dark" else LIGHT


def build_qss(p: Palette) -> str:
    return f"""
QWidget {{
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "SimHei", sans-serif;
    font-size: 13px;
    color: {p.text};
}}
QToolTip {{
    background: {p.surface};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px 9px;
}}

QFrame#card {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 14px;
}}
QFrame#softcard {{
    background: {p.surface2};
    border: none;
    border-radius: 12px;
}}
QFrame#tintcard {{
    background: {p.accent_soft};
    border: none;
    border-radius: 12px;
}}
QFrame#tealcard {{
    background: {p.teal_soft};
    border: none;
    border-radius: 12px;
}}

QLabel#h1 {{ font-size: 19px; font-weight: 600; }}
QLabel#h2 {{ font-size: 14px; font-weight: 600; }}
QLabel#muted {{ color: {p.muted}; }}
QLabel#faint {{ color: {p.faint}; font-size: 12px; }}
QLabel#mono {{ font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; }}
QLabel#badge {{
    background: {p.accent_soft};
    color: {p.accent};
    border-radius: 8px;
    padding: 3px 9px;
    font-size: 12px;
    font-weight: 600;
}}
QLabel#badgeTeal {{
    background: {p.teal_soft};
    color: {p.teal};
    border-radius: 8px;
    padding: 3px 9px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton {{
    background: transparent;
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 7px 13px;
    outline: none;
}}
QPushButton:hover {{ background: {p.surface2}; border-color: {p.border_strong}; }}
QPushButton:pressed {{ background: {p.surface3}; }}
QPushButton:disabled {{ color: {p.faint}; border-color: {p.border}; background: transparent; }}
QPushButton#primary {{
    background: {p.accent};
    color: {p.on_accent};
    border: none;
    font-weight: 600;
    padding: 9px 18px;
}}
QPushButton#primary:hover {{ background: {p.accent_hover}; }}
QPushButton#primary:disabled {{ background: {p.border_strong}; color: {p.surface}; }}
QPushButton#danger {{
    background: transparent;
    color: {p.danger};
    border: 1px solid {p.danger};
    font-weight: 600;
}}
QPushButton#danger:hover {{ background: {p.danger}; color: #FFFFFF; }}
QPushButton#quiet {{ border: none; background: transparent; padding: 5px 9px; }}
QPushButton#quiet:hover {{ background: {p.surface2}; }}
QPushButton#mini {{
    border: 1px solid {p.border_strong};
    background: {p.surface};
    border-radius: 8px;
    padding: 3px 10px;
    font-size: 12px;
}}
QPushButton#mini:hover {{ background: {p.surface3}; border-color: {p.accent}; }}
QPushButton#segment {{
    border: none;
    background: transparent;
    border-radius: 9px;
    padding: 7px 18px;
    color: {p.muted};
    font-weight: 600;
}}
QPushButton#segment[active="true"] {{ background: {p.surface}; color: {p.accent}; }}
QPushButton#segment:hover {{ background: {p.surface3}; }}

QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox {{
    background: {p.surface2};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 7px 10px;
    selection-background-color: {p.accent};
    selection-color: {p.on_accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border-color: {p.accent};
}}
QLineEdit:disabled, QComboBox:disabled {{ color: {p.faint}; background: {p.surface3}; }}
QLineEdit#flat {{ background: transparent; border: none; padding: 4px 6px; }}
QComboBox {{ padding-right: 24px; }}
QComboBox::drop-down {{ border: none; width: 22px; background: transparent; }}
QComboBox::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p.muted};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {p.surface};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 4px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.accent};
    outline: none;
}}

QCheckBox {{ color: {p.text}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 5px;
    border: 1px solid {p.border_strong};
    background: {p.surface2};
}}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

QScrollBar:vertical {{
    background: transparent; width: 9px; margin: 2px 2px 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {p.scroll}; border-radius: 4px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.border_strong}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 9px; margin: 0 2px 2px 2px;
}}
QScrollBar::handle:horizontal {{
    background: {p.scroll}; border-radius: 4px; min-width: 28px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QListWidget {{
    background: transparent; border: none; outline: none;
}}
QListWidget::item:selected {{ background: transparent; }}
QTextBrowser {{ border: none; background: transparent; padding: 0; }}
QPlainTextEdit#terminal {{
    background: {p.code_bg};
    color: {p.code_text};
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    border: 1px solid {p.border};
    border-radius: 12px;
    padding: 10px;
}}
QPlainTextEdit#log {{
    background: {p.code_bg};
    color: {p.muted};
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 11px;
    border: none;
    border-radius: 10px;
    padding: 8px;
}}
QSplitter::handle {{ background: transparent; }}
"""
