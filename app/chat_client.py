# -*- coding: utf-8 -*-
"""OpenAI 兼容 /v1/chat/completions 的 SSE 流式客户端（仅标准库）。

统计来源：
  - 实时 tok/s 与 TTFT：客户端按 SSE chunk 计时，生成过程中即可显示；
  - 精确值：llama-server 流式末块的 timings / usage（predicted_per_second 等）。
"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from PySide6.QtCore import QObject, Signal


class StreamClient(QObject):
    token = Signal(str)
    reasoning = Signal(str)
    stats = Signal(dict)
    done = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = threading.Event()
        self._resp = None
        self._thread: threading.Thread | None = None
        self.busy = False

    def send(self, base_url: str, api_key: str, model: str, messages: list[dict],
             max_tokens: int | None = None, temperature: float | None = None) -> None:
        if self.busy:
            return
        self._stop.clear()
        self.busy = True
        self._thread = threading.Thread(
            target=self._run,
            args=(base_url, api_key, model, list(messages), max_tokens, temperature),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        self._stop.set()
        resp = self._resp
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def _run(self, base_url: str, api_key: str, model: str, messages: list[dict],
             max_tokens: int | None, temperature: float | None) -> None:
        payload: dict[str, Any] = {
            "model": model or "local-model",
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        url = base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers=headers, method="POST")

        t0 = time.perf_counter()
        first: float | None = None
        count = 0
        timings: dict = {}
        usage: dict = {}
        error = ""

        try:
            self._resp = urllib.request.urlopen(req, timeout=90)
            for raw in self._resp:
                if self._stop.is_set():
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    if data == "[DONE]":
                        break
                    continue
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj.get("timings"), dict):
                    timings = obj["timings"]
                if isinstance(obj.get("usage"), dict):
                    usage = obj["usage"]
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content") or ""
                thought = delta.get("reasoning_content") or ""
                if not content and not thought:
                    continue
                count += 1
                now = time.perf_counter()
                if first is None:
                    first = now
                if thought:
                    self.reasoning.emit(thought)
                if content:
                    self.token.emit(content)
                if count % 4 == 0 and first is not None:
                    self.stats.emit({"live_tps": count / max(0.001, now - first),
                                    "ttft_ms": (first - t0) * 1000, "tokens": count})
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                body = ""
            error = f"HTTP {exc.code}: {body or exc.reason}"
        except (socket.timeout, TimeoutError):
            error = "请求超时（90 秒未收到数据）"
        except Exception as exc:
            if not self._stop.is_set():
                error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                if self._resp is not None:
                    self._resp.close()
            except Exception:
                pass
            self._resp = None

        elapsed = time.perf_counter() - t0
        span = max(0.001, elapsed if first is None else time.perf_counter() - first)
        local_tps = count / span
        final: dict[str, Any] = {
            "tokens": usage.get("completion_tokens") or count,
            "tps": timings.get("predicted_per_second") or local_tps,
            "live_tps": local_tps,
            "ttft_ms": (first - t0) * 1000 if first else 0.0,
            "elapsed": elapsed,
            "prompt_tps": timings.get("prompt_per_second"),
            "cached": timings.get("cache_n"),
            "total": usage.get("total_tokens"),
        }
        pn = timings.get("prompt_n") or 0
        cn = timings.get("cache_n") or 0
        dn = timings.get("predicted_n") or count
        final["ctx_used"] = pn + cn + dn
        self.stats.emit(final)
        self.busy = False
        if self._stop.is_set():
            self.done.emit(True, "已停止生成")
        else:
            self.done.emit(not bool(error), error)
