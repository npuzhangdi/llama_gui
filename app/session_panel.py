# -*- coding: utf-8 -*-
"""左侧「对话窗口」管理面板：项目、临时对话、归档、删除与新建对话框。

一个项目可以容纳多个对话；project_id 为空的对话是临时对话，不归入任何项目。
所有变更立即写入 SessionStore，并通过 activated / changed 通知主窗口切换视图。
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from .config import Config
from .sessions import SessionStore
from .theme import Palette


def _short(text: str, limit: int = 12) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


class NewSessionDialog(QDialog):
    """新建对话：可指定名称、归属项目（或临时）与本对话专属的系统提示词。"""

    def __init__(self, store: SessionStore, default_prompt: str, parent=None,
                 preselect_project: str = ""):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("新建对话")
        self.setMinimumWidth(400)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        title = QLabel("新建对话")
        title.setObjectName("h1")
        root.addWidget(title)
        hint = QLabel("临时对话不归入项目；每个对话可单独设置系统提示词。")
        hint.setObjectName("faint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(QLabel("对话名称"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("留空则自动生成，也可用首条消息作为标题")
        root.addWidget(self.title_edit)

        root.addWidget(QLabel("归属项目"))
        self.project_combo = QComboBox()
        self.project_combo.addItem("临时对话（不归入项目）", "")
        for p in store.projects():
            self.project_combo.addItem(p["name"], p["id"])
        self.project_combo.addItem("＋ 新建项目…", "__new__")
        if preselect_project:
            idx = self.project_combo.findData(preselect_project)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        root.addWidget(self.project_combo)

        self.new_project_edit = QLineEdit()
        self.new_project_edit.setPlaceholderText("新项目名称")
        self.new_project_edit.setVisible(False)
        root.addWidget(self.new_project_edit)

        root.addWidget(QLabel("系统提示词（仅作用于本对话）"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlainText(default_prompt)
        self.prompt_edit.setFixedHeight(86)
        root.addWidget(self.prompt_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("创建")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._on_project_changed(self.project_combo.currentIndex())

    def _on_project_changed(self, _index: int) -> None:
        self.new_project_edit.setVisible(self.project_combo.currentData() == "__new__")

    def result_data(self) -> tuple[str, str, str]:
        """返回 (名称, 项目 id, 系统提示词)；必要时创建项目。"""
        pid = str(self.project_combo.currentData() or "")
        if pid == "__new__":
            name = self.new_project_edit.text().strip() or "新项目"
            pid = self.store.create_project(name)["id"]
        return (self.title_edit.text().strip(), pid,
                self.prompt_edit.toPlainText())


class SessionPanel(QWidget):
    activated = Signal(str)
    changed = Signal()

    def __init__(self, store: SessionStore, cfg: Config, pal: Palette, parent=None):
        super().__init__(parent)
        self.store = store
        self.cfg = cfg
        self.pal = pal
        self._temp_collapsed = False
        self._show_archived = False

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 0, 2, 0)
        root.setSpacing(6)

        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 0, 0)
        head.setSpacing(4)
        label = QLabel("对话窗口")
        label.setObjectName("h2")
        head.addWidget(label)
        head.addStretch(1)
        self.new_btn = self._mini_button("＋", "新建对话", self._new_session)
        self.project_btn = self._mini_button("▣", "新建项目", self._new_project)
        head.addWidget(self.new_btn)
        head.addWidget(self.project_btn)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root.addWidget(self.scroll, 1)

        self.archive_btn = QPushButton("已归档")
        self.archive_btn.setObjectName("quiet")
        self.archive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.archive_btn.clicked.connect(self._toggle_archived)
        root.addWidget(self.archive_btn)

        self.refresh()

    # ---------------- 小工具 ----------------
    def _mini_button(self, text: str, tooltip: str, callback) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("quiet")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        self._style_mini(btn)
        return btn

    def _style_mini(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {self.pal.muted};"
            f" padding: 0; font-size: 14px; }}"
            f"QPushButton:hover {{ background: {self.pal.surface3}; border-radius: 6px;"
            f" color: {self.pal.accent}; }}")

    def _group(self, title: str, count: int, collapsed: bool, on_toggle,
               extras: list[QPushButton]) -> QFrame:
        row = QFrame()
        row.setFixedHeight(28)
        box = QHBoxLayout(row)
        box.setContentsMargins(2, 0, 0, 0)
        box.setSpacing(2)
        btn = QPushButton(("▸  " if collapsed else "▾  ") + _short(title, 10))
        btn.setObjectName("quiet")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(title)
        btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {self.pal.muted};"
            f" text-align: left; padding: 2px 2px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ color: {self.pal.text}; }}")
        btn.clicked.connect(on_toggle)
        box.addWidget(btn, 1)
        num = QLabel(str(count))
        num.setObjectName("faint")
        box.addWidget(num)
        for extra in extras:
            box.addWidget(extra)
        return row

    def _session_row(self, session: dict) -> QFrame:
        sid = session["id"]
        active = sid == self.store.active_id()
        archived = bool(session["archived"])
        row = QFrame()
        row.setFixedHeight(29)
        row.setObjectName("sessionRow")
        bg = self.pal.accent_soft if active else "transparent"
        row.setStyleSheet(f"QFrame#sessionRow {{ background: {bg}; border-radius: 8px; }}")
        box = QHBoxLayout(row)
        box.setContentsMargins(4, 0, 2, 0)
        box.setSpacing(0)

        title = QPushButton("   " + _short(session["title"], 12))
        title.setObjectName("quiet")
        title.setCursor(Qt.CursorShape.PointingHandCursor)
        title.setToolTip(session["title"] + ("（已归档）" if archived else ""))
        color = self.pal.accent if active else (self.pal.muted if archived else self.pal.text)
        title.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {color};"
            f" text-align: left; padding: 2px 2px; }}"
            f"QPushButton:hover {{ color: {self.pal.accent}; }}")
        title.clicked.connect(lambda _=False, s=sid: self._activate(s))
        box.addWidget(title, 1)

        more = self._mini_button("⋯", "管理此对话", lambda: self._session_menu(sid, more))
        box.addWidget(more)
        row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        row.customContextMenuRequested.connect(
            lambda pos, s=sid, r=row: self._session_menu(s, r, pos))
        return row

    # ---------------- 列表渲染 ----------------
    def refresh(self) -> None:
        old = self.scroll.takeWidget()
        if old is not None:
            old.setParent(None)
            old.deleteLater()
        host = QWidget()
        host.setObjectName("sessionHost")
        host.setStyleSheet(f"QWidget#sessionHost {{ background: transparent; }}")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 2, 0)
        lay.setSpacing(2)

        temp = self.store.list_sessions("", archived=False)
        add_temp = self._mini_button("＋", "新建临时对话", lambda: self._new_session(""))
        lay.addWidget(self._group("临时对话", len(temp), self._temp_collapsed,
                                  self._toggle_temp, [add_temp]))
        if not self._temp_collapsed:
            for s in temp:
                lay.addWidget(self._session_row(s))
            if not temp:
                lay.addWidget(self._empty_label("暂无临时对话"))

        for p in self.store.projects():
            pid = p["id"]
            items = self.store.list_sessions(pid, archived=False)
            add = self._mini_button("＋", f"在「{p['name']}」中新建对话",
                                    lambda _=False, x=pid: self._new_session(x))
            more = self._mini_button("⋯", "管理此项目", lambda: None)
            more.clicked.disconnect()
            more.clicked.connect(lambda _=False, x=pid, b=more: self._project_menu(x, b))
            collapsed = bool(p.get("collapsed"))
            lay.addWidget(self._group(p["name"], len(items), collapsed,
                                      lambda _=False, x=pid: self._toggle_project(x),
                                      [add, more]))
            if not collapsed:
                for s in items:
                    lay.addWidget(self._session_row(s))
                if not items:
                    lay.addWidget(self._empty_label("暂无对话"))

        archived_count = self.store.count_archived()
        self.archive_btn.setText(f"已归档 ({archived_count})  {'▴' if self._show_archived else '▾'}")
        self.archive_btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {self.pal.faint};"
            f" text-align: left; padding: 3px 4px; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {self.pal.accent}; }}")
        if self._show_archived:
            archived = self.store.list_sessions(None, archived=True)
            for s in archived:
                lay.addWidget(self._session_row(s))
            if not archived:
                lay.addWidget(self._empty_label("暂无归档对话"))

        lay.addStretch(1)
        self.scroll.setWidget(host)

    def _empty_label(self, text: str) -> QLabel:
        lab = QLabel("    " + text)
        lab.setObjectName("faint")
        lab.setFixedHeight(22)
        return lab

    def _toggle_temp(self) -> None:
        self._temp_collapsed = not self._temp_collapsed
        self.refresh()

    def _toggle_project(self, pid: str) -> None:
        p = self.store.project(pid)
        if p:
            self.store.set_project_collapsed(pid, not bool(p.get("collapsed")))
            self.refresh()

    def _toggle_archived(self) -> None:
        self._show_archived = not self._show_archived
        self.refresh()

    # ---------------- 菜单 ----------------
    def _session_menu(self, sid: str, anchor: QWidget, pos: QPoint | None = None) -> None:
        session = self.store.get(sid)
        if not session:
            return
        menu = QMenu(anchor)
        menu.addAction("重命名", lambda: self._rename_session(sid))
        move = menu.addMenu("移动到项目")
        move.addAction("临时对话（不归入项目）", lambda: self._move(sid, ""))
        for p in self.store.projects():
            move.addAction(p["name"], lambda pid=p["id"]: self._move(sid, pid))
        menu.addSeparator()
        archived = bool(session["archived"])
        menu.addAction("取消归档" if archived else "归档",
                       lambda: self._archive(sid, not archived))
        menu.addSeparator()
        menu.addAction("删除", lambda: self._delete_session(sid))
        point = anchor.mapToGlobal(pos) if pos is not None else \
            anchor.mapToGlobal(QPoint(0, anchor.height()))
        menu.exec(point)

    def _project_menu(self, pid: str, anchor: QWidget) -> None:
        project = self.store.project(pid)
        if not project:
            return
        menu = QMenu(anchor)
        menu.addAction("在此项目新建对话", lambda: self._new_session(pid))
        menu.addAction("重命名项目", lambda: self._rename_project(pid))
        menu.addSeparator()
        menu.addAction("删除项目（对话转为临时）", lambda: self._delete_project(pid))
        menu.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))

    # ---------------- 操作 ----------------
    def _new_session(self, preselect_project: str = "") -> None:
        dlg = NewSessionDialog(self.store, str(self.cfg.get("system_prompt") or ""),
                               self, preselect_project)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        title, pid, prompt = dlg.result_data()
        session = self.store.create_session(pid, title, prompt)
        self._sync_active(session["id"])

    def _new_project(self) -> None:
        name, ok = QInputDialog.getText(self, "新建项目", "项目名称：")
        if ok and name.strip():
            self.store.create_project(name)
            self.refresh()
            self.changed.emit()

    def _rename_project(self, pid: str) -> None:
        p = self.store.project(pid)
        if not p:
            return
        name, ok = QInputDialog.getText(self, "重命名项目", "项目名称：", text=p["name"])
        if ok and name.strip():
            self.store.rename_project(pid, name)
            self.refresh()
            self.changed.emit()

    def _delete_project(self, pid: str) -> None:
        p = self.store.project(pid)
        if not p:
            return
        answer = QMessageBox.question(
            self, "删除项目",
            f"删除项目「{p['name']}」？\n其中的对话会保留并转为临时对话。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.store.delete_project(pid)
            self.refresh()
            self.changed.emit()

    def _rename_session(self, sid: str) -> None:
        s = self.store.get(sid)
        if not s:
            return
        name, ok = QInputDialog.getText(self, "重命名对话", "对话名称：", text=s["title"])
        if ok and name.strip():
            self.store.rename_session(sid, name)
            self.refresh()
            self.changed.emit()

    def _move(self, sid: str, pid: str) -> None:
        self.store.move_session(sid, pid)
        self.refresh()
        self.changed.emit()

    def _archive(self, sid: str, value: bool) -> None:
        self.store.set_archived(sid, value)
        self._sync_active()

    def _delete_session(self, sid: str) -> None:
        s = self.store.get(sid)
        if not s:
            return
        answer = QMessageBox.question(
            self, "删除对话", f"确定删除「{s['title']}」？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.store.delete_session(sid)
            self._sync_active()

    def _activate(self, sid: str) -> None:
        self._sync_active(sid)

    def _sync_active(self, sid: str | None = None) -> None:
        target = sid or self.store.active_id()
        if not target or not self.store.get(target):
            self.store.ensure_default(str(self.cfg.get("system_prompt") or ""))
            target = self.store.active_id()
        self.store.set_active(target)
        self.refresh()
        self.changed.emit()
        self.activated.emit(target)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self._style_mini(self.new_btn)
        self._style_mini(self.project_btn)
        self.refresh()
