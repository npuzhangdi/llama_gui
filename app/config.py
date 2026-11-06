# -*- coding: utf-8 -*-
"""配置持久化与 GGUF 模型扫描。

配置文件位于程序根目录（v0.0.1/llama_gui_config.json），字段兼容 v0.0.0。
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CONFIG_NAME = "llama_gui_config.json"


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


DEFAULTS = {
    "program_type": "llama-server",
    "path_llama-server": "",
    "path_llama-cli": "",
    "scan_dir": "",
    "model": "",
    "host": "127.0.0.1",
    "port": "8080",
    "ngl": "99",
    "ctx": "",
    "threads": "",
    "fa": "auto",
    "alias": "",
    "api_key": "",
    # 高级参数
    "batch": "",
    "ubatch": "",
    "predict": "",
    "temp": "",
    "top_p": "",
    "top_k": "",
    "seed": "",
    "reasoning": "off",
    "nparallel": "",
    "ssl_key": "",
    "ssl_cert": "",
    "no_mmap": False,
    "load_mode": "",
    "verbose": False,
    "custom": "",
    # 界面
    "theme": "light",
    "glass": True,
    "system_prompt": "You are a helpful assistant.",
    "max_tokens": "",
    "temperature": "",
}

_QUANT_RE = re.compile(
    r"(?:^|[-_])(IQ\d+_[A-Z0-9_]+|Q\d+_K_[A-Z]+|Q\d+_[A-Z0-9_]+|Q\d+|BF16|F16|F32|FP16)",
    re.IGNORECASE,
)


@dataclass
class ModelInfo:
    path: Path
    name: str
    size: int
    modified: str

    @property
    def size_text(self) -> str:
        gb = self.size / (1024 ** 3)
        return f"{gb:.2f} GB" if gb >= 1 else f"{self.size / (1024 ** 2):.0f} MB"

    @property
    def quant(self) -> str:
        m = _QUANT_RE.search(self.name)
        return m.group(1).upper() if m else "GGUF"

    @property
    def path_text(self) -> str:
        return str(self.path)


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or (base_dir() / CONFIG_NAME)
        self.data = dict(DEFAULTS)
        self.load()
        self._migrate()
        self._autofill_paths()

    def _migrate(self) -> None:
        """旧版 --no-mmap 已在本机 llama.cpp 中改为 -lm none。"""
        if self.data.get("no_mmap") and not self.data.get("load_mode"):
            self.data["load_mode"] = "none"
            self.data["no_mmap"] = False

    def load(self) -> None:
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    self.data.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except Exception as exc:  # 配置损坏不应阻止启动
            print(f"[config] 读取失败: {exc}")

    def save(self) -> None:
        try:
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"[config] 保存失败: {exc}")

    def get(self, key: str, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def update(self, values: dict) -> None:
        for k, v in values.items():
            if k in DEFAULTS:
                self.data[k] = v

    def _autofill_paths(self) -> None:
        """若 CLI 路径为空但 server 路径有效，自动补全同目录的 llama-cli.exe。"""
        cli = str(self.get("path_llama-cli", "")).strip()
        srv = str(self.get("path_llama-server", "")).strip()
        if not cli and srv:
            candidate = Path(srv).parent / "llama-cli.exe"
            if candidate.is_file():
                self.set("path_llama-cli", str(candidate))

    def program_path(self) -> str:
        key = f"path_{self.get('program_type')}"
        return str(self.get(key, "")).strip()

    def set_program_path(self, value: str) -> None:
        self.set(f"path_{self.get('program_type')}", value)

    def base_url(self) -> str:
        host = str(self.get("host") or "127.0.0.1").strip()
        port = str(self.get("port") or "8080").strip()
        shown = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
        return f"http://{shown}:{port}/v1"

    def scan_models(self) -> list[ModelInfo]:
        folder = str(self.get("scan_dir", "")).strip()
        if not folder:
            return []
        root = Path(folder)
        if not root.is_dir():
            return []
        result: list[ModelInfo] = []
        try:
            for p in sorted(root.rglob("*.gguf")):
                stat = p.stat()
                result.append(
                    ModelInfo(
                        path=p,
                        name=p.name,
                        size=stat.st_size,
                        modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                    )
                )
        except OSError as exc:
            print(f"[config] 扫描失败: {exc}")
        return result
