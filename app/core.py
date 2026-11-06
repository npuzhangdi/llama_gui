# -*- coding: utf-8 -*-
"""llama-server / llama-cli 双模式进程管理与命令行参数拼装。"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .config import Config


@dataclass(frozen=True)
class ParamSpec:
    key: str
    flag: str
    label: str
    placeholder: str = ""
    server: bool = True
    cli: bool = True
    kind: str = "text"
    options: tuple = ()


MAIN_PARAMS = (
    ParamSpec("host", "--host", "绑定地址", "127.0.0.1", cli=False),
    ParamSpec("port", "--port", "端口", "8080", cli=False),
    ParamSpec("ngl", "-ngl", "GPU 层数", "99"),
    ParamSpec("ctx", "-c", "上下文长度", "0 = 从模型读取"),
    ParamSpec("threads", "-t", "CPU 线程数", "默认 = 物理核心数"),
    ParamSpec("fa", "-fa", "Flash Attention", kind="combo", options=("", "auto", "on", "off")),
    ParamSpec("alias", "--alias", "模型别名", "供 /v1/models 显示", cli=False),
    ParamSpec("api_key", "--api-key", "API 密钥", "可选，留空不鉴权", cli=False),
)

ADV_PARAMS = (
    ParamSpec("batch", "-b", "逻辑批大小", "默认 2048"),
    ParamSpec("ubatch", "-ub", "物理批大小", "默认 512"),
    ParamSpec("predict", "-n", "最大生成数", "-1 = 不限制"),
    ParamSpec("temp", "--temp", "温度", "默认 0.8"),
    ParamSpec("top_p", "--top-p", "Top-p", "默认 0.95"),
    ParamSpec("top_k", "--top-k", "Top-k", "默认 40"),
    ParamSpec("seed", "-s", "随机种子", "-1 = 随机"),
    ParamSpec("reasoning", "--reasoning", "思考模式", kind="combo", options=("", "auto", "on", "off")),
    ParamSpec("nparallel", "-np", "并行 slot 数", "默认 1", cli=False),
    ParamSpec("ssl_key", "--ssl-key-file", "SSL 私钥", kind="file", cli=False),
    ParamSpec("ssl_cert", "--ssl-cert-file", "SSL 证书", kind="file", cli=False),
    ParamSpec("load_mode", "-lm", "模型加载模式", kind="combo",
              options=("", "auto", "none", "mmap", "mlock", "mmap+mlock")),
    ParamSpec("verbose", "-v", "详细日志", kind="bool"),
)

ALL_PARAMS = MAIN_PARAMS + ADV_PARAMS
PARAM_BY_KEY = {p.key: p for p in ALL_PARAMS}


def split_extra(text: str) -> list[str]:
    """按空格切分自定义参数，保留引号内的 Windows 反斜杠路径。"""
    if not text.strip():
        return []
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"') else t
            for t in re.findall(r'"[^"]*"|\'[^\']*\'|\S+', text.strip())]


def build_args(cfg: Config, program_type: str | None = None) -> list[str]:
    """按程序类型过滤参数：server 专属参数不会误传给 llama-cli。"""
    pt = program_type or cfg.get("program_type")
    is_server = pt == "llama-server"
    args: list[str] = []
    model = str(cfg.get("model", "") or "").strip()
    if model:
        args += ["-m", model]
    for spec in ALL_PARAMS:
        if not (spec.server if is_server else spec.cli):
            continue
        if spec.kind == "bool":
            if bool(cfg.get(spec.key, False)):
                args.append(spec.flag)
            continue
        value = str(cfg.get(spec.key, "") or "").strip()
        if value:
            args += [spec.flag, value]
    args += split_extra(str(cfg.get("custom", "") or ""))
    return args


def preview_command(program: str, args: list[str]) -> str:
    parts = [f'"{program}"']
    parts += [f'"{a}"' if (" " in a or "\t" in a) else a for a in args]
    return " ".join(parts)


_TPS_RE = re.compile(r"([\d.]+)\s*tokens\s*per\s*second", re.IGNORECASE)
_SHORT_TPS_RE = re.compile(r"Generation:\s*([\d.]+)\s*t/s", re.IGNORECASE)


def parse_cli_tps(line: str) -> float | None:
    """兼容两种 llama.cpp 速率日志：
    - 新版交互摘要： [ Prompt: 324.4 t/s | Generation: 57.6 t/s ]
    - 旧版 perf 行： eval time = ... / 35 tokens / 28.34 tokens per second
    """
    short = _SHORT_TPS_RE.search(line)
    if short:
        try:
            return float(short.group(1))
        except ValueError:
            return None
    if "tokens per second" not in line.lower():
        return None
    found = _TPS_RE.findall(line)
    if not found:
        return None
    try:
        return float(found[-1])
    except ValueError:
        return None


def probe_health(base_url: str, timeout: float = 0.6) -> bool:
    """GET /health，200 表示 llama-server 已就绪。"""
    import urllib.request
    url = base_url[:-2] + "health" if base_url.endswith("/v1") else base_url.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


class ProcManager(QObject):
    output = Signal(str)
    state_changed = Signal(str)
    finished = Signal(int)
    perf = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._state = "idle"

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def state(self) -> str:
        return self._state

    def _set_state(self, value: str) -> None:
        if value != self._state:
            self._state = value
            self.state_changed.emit(value)

    def start(self, program: str, args: list[str]) -> tuple[bool, str]:
        if self.is_running():
            return False, "进程已在运行"
        path = Path(program.strip())
        if not program.strip():
            return False, "请先设置程序路径"
        if not path.is_file():
            return False, f"程序路径不存在：\n{program}"

        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        # exe 依赖同目录 DLL，需把工作目录设为 exe 所在目录
        try:
            self.proc = subprocess.Popen(
                [program] + args,
                cwd=str(path.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                creationflags=flags,
                bufsize=0,
            )
        except Exception as exc:
            self.proc = None
            return False, f"启动失败：{exc}"

        self._set_state("running")
        self.output.emit(f"$ {preview_command(program, args)}\n\n")
        proc = self.proc
        self._thread = threading.Thread(target=self._reader, args=(proc,), daemon=True)
        self._thread.start()
        return True, ""

    def _reader(self, proc: subprocess.Popen) -> None:
        """子进程输出读取；窗口关闭时 stdout 会被系统回收，此处需静默处理。"""
        try:
            stream = proc.stdout
            if stream is not None:
                for raw in iter(stream.readline, b""):
                    try:
                        text = raw.decode("utf-8", errors="replace")
                        self.output.emit(text)
                        rate = parse_cli_tps(text)
                        if rate is not None:
                            self.perf.emit(rate)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            try:
                code = proc.wait(timeout=5)
            except Exception:
                code = -1
            try:
                self.finished.emit(code)
            except Exception:
                pass

    def on_finished(self, code: int) -> None:
        """主线程槽：清理引用并广播空闲状态。"""
        self.output.emit(f"\n[进程结束] 退出码 = {code}\n")
        self.proc = None
        self._thread = None
        self._set_state("idle")

    def stop(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        self._set_state("stopping")
        self.output.emit("\n[正在停止…]\n")
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.output.emit("[超时，强制结束]\n")
                proc.kill()
                proc.wait(timeout=3)
        except Exception as exc:
            self.output.emit(f"[停止异常] {exc}\n")

    def send(self, text: str) -> tuple[bool, str]:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return False, "进程未在运行"
        try:
            proc.stdin.write((text + "\n").encode("utf-8"))
            proc.stdin.flush()
            return True, ""
        except Exception as exc:
            return False, f"写入标准输入失败：{exc}"

    def shutdown(self) -> None:
        if self.is_running():
            try:
                self.proc.kill()
                self.proc.wait(timeout=2)
            except Exception:
                pass
        self.proc = None
