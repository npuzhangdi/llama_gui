# -*- coding: utf-8 -*-
"""配置持久化与 GGUF 模型扫描。

所有程序内路径都相对可执行文件/源码目录解析，不含任何绝对路径：
- 配置文件：程序根目录 / llama_gui_config.json
- llama.cpp 目录：llama_dir 配置 → 环境变量 → llama_dir.txt → PATH → 程序相邻目录
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CONFIG_NAME = "llama_gui_config.json"


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _has_gguf(folder: Path) -> bool:
    """只扫描两层，避免对大目录做无界递归。"""
    try:
        return bool(next(folder.glob("*.gguf"), None)) or bool(next(folder.glob("*/*.gguf"), None))
    except (OSError, StopIteration):
        return False


def detect_llama_dir() -> str:
    """按优先级自动探测 llama.cpp 发行目录；全部路径均为运行时推导。"""
    root = base_dir()
    candidates: list[Path] = []

    for name in ("LLAMA_CPP_DIR", "LLAMA_DIR", "LLAMA_SERVER_DIR"):
        value = os.environ.get(name, "").strip().strip('"')
        if value:
            candidates.append(Path(value))

    marker = root / "llama_dir.txt"
    if marker.is_file():
        try:
            value = marker.read_text(encoding="utf-8").strip().strip('"')
            if value and not value.startswith("#"):
                candidates.append(Path(value))
        except OSError:
            pass

    found = shutil.which("llama-server.exe")
    if found:
        candidates.append(Path(found).parent)

    for rel in ("llama", "llama.cpp", "llama-cpp", "bin", "runtime"):
        candidates.append(root / rel)
    for rel in ("llama", "llama.cpp", "llama-cpp"):
        candidates.append(root.parent / rel)

    for path in candidates:
        try:
            if path.is_dir() and (path / "llama-server.exe").is_file():
                return str(path)
        except OSError:
            continue
    return ""


DEFAULTS = {
    "program_type": "llama-server",
    "llama_dir": "",                 # 程序/模型等外部资源路径由用户指定，不写入绝对路径
    "path_llama-server": "",
    "path_llama-cli": "",
    "scan_dir": "",
    "model": "",
    # 常用参数
    "host": "127.0.0.1",
    "port": "8080",
    "ngl": "99",
    "ctx": "",
    "threads": "",
    "fa": "auto",
    "alias": "",
    "api_key": "",
    # 原高级参数（其余新参数按需动态写入，无需预先枚举）
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
    "param_group": "all",
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
        """接受配置文件中的任意键，新增参数无需改动本模块。"""
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    self.data.update(saved)
        except Exception as exc:
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
        self.data.update(values)

    # ---------------- 路径解析 ----------------
    def _autofill_paths(self) -> None:
        folder = str(self.get("llama_dir", "") or "").strip() or detect_llama_dir()
        if not folder:
            return
        self.set("llama_dir", folder)
        base = Path(folder)
        for kind in ("llama-server", "llama-cli"):
            key = f"path_{kind}"
            if not str(self.get(key, "") or "").strip():
                candidate = base / f"{kind}.exe"
                if candidate.is_file():
                    self.set(key, str(candidate))
        if not str(self.get("scan_dir", "") or "").strip():
            for candidate in (base, base.parent):
                if _has_gguf(candidate):
                    self.set("scan_dir", str(candidate))
                    break

    def set_llama_dir(self, value: str) -> None:
        folder = value.strip()
        self.set("llama_dir", folder)
        if folder:
            base = Path(folder)
            for kind in ("llama-server", "llama-cli"):
                self.set(f"path_{kind}", str(base / f"{kind}.exe"))
            if not str(self.get("scan_dir", "") or "").strip():
                for candidate in (base, base.parent):
                    if _has_gguf(candidate):
                        self.set("scan_dir", str(candidate))
                        break

    def program_path(self, program_type: str | None = None) -> str:
        """取指定模式的可执行文件；不传则取当前选中的模式。"""
        pt = program_type or self.get("program_type")
        key = f"path_{pt}"
        value = str(self.get(key, "") or "").strip()
        if value:
            return value
        folder = str(self.get("llama_dir", "") or "").strip()
        if folder:
            return str(Path(folder) / f"{pt}.exe")
        return ""

    def set_program_path(self, value: str) -> None:
        text = value.strip()
        self.set(f"path_{self.get('program_type')}", text)
        if text:
            path = Path(text)
            self.set("llama_dir", str(path.parent))

    def base_url(self) -> str:
        host = str(self.get("host") or "127.0.0.1").strip()
        port = str(self.get("port") or "8080").strip()
        shown = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
        return f"http://{shown}:{port}/v1"

    def scan_models(self) -> list[ModelInfo]:
        folder = str(self.get("scan_dir", "") or "").strip()
        if folder:
            roots = [Path(folder)]
        else:
            llama = str(self.get("llama_dir", "") or "").strip()
            roots = [Path(llama), Path(llama).parent] if llama else []

        seen: set[str] = set()
        paths: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            try:
                iterator = root.rglob("*.gguf") if folder else (
                    list(root.glob("*.gguf")) + list(root.glob("*/*.gguf"))
                )
                for p in iterator:
                    key = str(p).lower()
                    if key not in seen:
                        seen.add(key)
                        paths.append(p)
            except OSError as exc:
                print(f"[config] 扫描失败: {exc}")

        result: list[ModelInfo] = []
        for p in sorted(paths):
            try:
                stat = p.stat()
                result.append(ModelInfo(
                    path=p,
                    name=p.name,
                    size=stat.st_size,
                    modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                ))
            except OSError:
                continue
        return result
