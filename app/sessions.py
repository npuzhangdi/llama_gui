# -*- coding: utf-8 -*-
"""对话窗口（会话）与项目的持久化存储。

数据保存在程序目录 data/sessions.json，全部路径由 base_dir() 运行时推导，
不含任何绝对路径，目录整体复制到另一台电脑后数据随程序一起迁移。

结构：
    projects   项目列表，一个项目可包含多个对话
    sessions   对话列表；project_id 为空表示「临时对话」（不归入项目）
    archived   归档标记；归档后从主列表移出，可在「已归档」分组中恢复
    每个对话独立保存 system_prompt 与 messages，因此不同窗口互不干扰。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from .config import base_dir

DATA_DIR = "data"
FILE_NAME = "sessions.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _uid() -> str:
    return uuid.uuid4().hex[:12]


class SessionStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (base_dir() / DATA_DIR / FILE_NAME)
        self.data: dict = {
            "version": 1,
            "active_id": "",
            "projects": [],
            "sessions": [],
        }
        self.load()
        self.normalize()

    # ---------------- 持久化 ----------------
    def load(self) -> None:
        try:
            if self.path.is_file():
                saved = json.loads(self.path.read_text("utf-8"))
                if isinstance(saved, dict):
                    self.data.update(saved)
        except Exception as exc:
            print(f"[sessions] read failed: {exc}")

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        except Exception as exc:
            print(f"[sessions] save failed: {exc}")

    # ---------------- 校验 ----------------
    def normalize(self) -> None:
        projects = [p for p in self.data.get("projects", []) if isinstance(p, dict) and p.get("id")]
        sessions = [s for s in self.data.get("sessions", []) if isinstance(s, dict) and s.get("id")]
        self.data["projects"] = projects
        self.data["sessions"] = sessions
        ids = {p["id"] for p in projects}
        for s in sessions:
            s.setdefault("title", "新对话")
            s.setdefault("project_id", "")
            s.setdefault("system_prompt", "")
            s.setdefault("messages", [])
            s.setdefault("archived", False)
            s.setdefault("created", _now())
            s.setdefault("updated", s["created"])
            if s["project_id"] not in ids:
                s["project_id"] = ""
            if not isinstance(s["messages"], list):
                s["messages"] = []
        for p in projects:
            p.setdefault("name", "项目")
            p.setdefault("created", _now())
            p.setdefault("collapsed", False)
        active = str(self.data.get("active_id") or "")
        if not self._by_id(active) or self._by_id(active)["archived"]:
            self.data["active_id"] = self._first_visible()

    def _by_id(self, sid: str) -> dict | None:
        return next((s for s in self.data["sessions"] if s["id"] == sid), None)

    def _first_visible(self) -> str:
        for s in sorted(self.data["sessions"], key=lambda x: x.get("updated", ""), reverse=True):
            if not s["archived"]:
                return s["id"]
        return ""

    # ---------------- 项目 ----------------
    def projects(self) -> list[dict]:
        return sorted(self.data["projects"], key=lambda p: p.get("created", ""))

    def project(self, pid: str) -> dict | None:
        return next((p for p in self.data["projects"] if p["id"] == pid), None)

    def project_name(self, pid: str) -> str:
        p = self.project(pid)
        return p["name"] if p else "临时对话"

    def create_project(self, name: str) -> dict:
        project = {"id": _uid(), "name": (name or "新项目").strip(),
                   "created": _now(), "collapsed": False}
        self.data["projects"].append(project)
        self.save()
        return project

    def rename_project(self, pid: str, name: str) -> None:
        p = self.project(pid)
        if p and name.strip():
            p["name"] = name.strip()
            self.save()

    def set_project_collapsed(self, pid: str, value: bool) -> None:
        p = self.project(pid)
        if p:
            p["collapsed"] = bool(value)
            self.save()

    def delete_project(self, pid: str) -> None:
        """删除项目但保留其中的对话，全部转为临时对话。"""
        self.data["projects"] = [p for p in self.data["projects"] if p["id"] != pid]
        for s in self.data["sessions"]:
            if s["project_id"] == pid:
                s["project_id"] = ""
                s["updated"] = _now()
        self.save()

    # ---------------- 对话 ----------------
    def _next_title(self) -> str:
        used = {s.get("title", "") for s in self.data["sessions"]}
        n = 1
        while f"新对话 {n}" in used:
            n += 1
        return f"新对话 {n}"

    def create_session(self, project_id: str = "", title: str = "",
                       system_prompt: str = "") -> dict:
        session = {
            "id": _uid(),
            "title": (title or self._next_title()).strip(),
            "project_id": project_id if self.project(project_id) else "",
            "system_prompt": system_prompt,
            "messages": [],
            "archived": False,
            "created": _now(),
            "updated": _now(),
        }
        self.data["sessions"].append(session)
        self.save()
        return session

    def ensure_default(self, default_prompt: str = "") -> None:
        if not self.data["sessions"]:
            session = self.create_session("", "新对话 1", default_prompt)
            self.data["active_id"] = session["id"]
            self.save()
        elif not self.data.get("active_id"):
            self.data["active_id"] = self._first_visible()
            self.save()

    def get(self, sid: str) -> dict:
        s = self._by_id(sid)
        if s is None:
            return {}
        return {
            **s,
            "messages": [dict(m) for m in s["messages"]],
        }

    def active_id(self) -> str:
        return str(self.data.get("active_id") or "")

    def active(self) -> dict:
        return self.get(self.active_id())

    def set_active(self, sid: str) -> None:
        if self._by_id(sid):
            self.data["active_id"] = sid
            self.save()

    def list_sessions(self, project_id: str | None = None, archived: bool = False) -> list[dict]:
        result = [
            s for s in self.data["sessions"]
            if bool(s["archived"]) == archived
            and (project_id is None or s["project_id"] == project_id)
        ]
        return sorted(result, key=lambda s: (s.get("updated", ""), s.get("created", "")),
                      reverse=True)

    def count_archived(self) -> int:
        return sum(1 for s in self.data["sessions"] if s["archived"])

    def rename_session(self, sid: str, title: str) -> None:
        s = self._by_id(sid)
        if s and title.strip():
            s["title"] = title.strip()
            s["updated"] = _now()
            self.save()

    def set_prompt(self, sid: str, text: str, save: bool = True) -> None:
        s = self._by_id(sid)
        if s:
            s["system_prompt"] = text
            if save:
                self.save()

    def update_content(self, sid: str, messages: list[dict],
                       system_prompt: str | None = None) -> None:
        s = self._by_id(sid)
        if not s:
            return
        s["messages"] = [dict(m) for m in messages]
        if system_prompt is not None:
            s["system_prompt"] = system_prompt
        s["updated"] = _now()
        # 首条用户消息自动作为对话标题，避免列表里全是「新对话 N」
        if s["title"].startswith("新对话"):
            first = next((m.get("content", "") for m in s["messages"]
                          if m.get("role") == "user" and m.get("content")), "")
            if first:
                one_line = " ".join(first.split())[:18]
                s["title"] = one_line + ("…" if len(" ".join(first.split())) > 18 else "")
        self.save()

    def move_session(self, sid: str, project_id: str) -> None:
        s = self._by_id(sid)
        if s:
            s["project_id"] = project_id if self.project(project_id) else ""
            s["updated"] = _now()
            self.save()

    def set_archived(self, sid: str, value: bool) -> None:
        s = self._by_id(sid)
        if not s:
            return
        s["archived"] = bool(value)
        s["updated"] = _now()
        if value and self.data.get("active_id") == sid:
            self.data["active_id"] = self._first_visible()
        self.save()

    def delete_session(self, sid: str) -> None:
        self.data["sessions"] = [s for s in self.data["sessions"] if s["id"] != sid]
        if self.data.get("active_id") == sid:
            self.data["active_id"] = self._first_visible()
        if not self.data["sessions"]:
            self.ensure_default()
        self.save()
