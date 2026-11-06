# -*- coding: utf-8 -*-
"""llama-server / llama-cli 双模式进程管理与命令行参数拼装。

参数表按 llama.cpp b10950 的 --help 校准，并按用途分组；
服务页通过 group / kind 字段自动生成控件，无需为每个参数写 UI 代码。
"""
from __future__ import annotations

import re
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
    kind: str = "text"          # text | combo | bool | file | dir
    options: tuple = ()
    group: str = "perf"         # main | sampling | perf | cache | server | extra | cli


def P(key, flag, label, placeholder="", group="perf", kind="text",
      options=(), server=True, cli=True) -> ParamSpec:
    return ParamSpec(key, flag, label, placeholder, server, cli, kind, tuple(options), group)


# 分组顺序即服务页标签顺序
GROUPS = (
    ("sampling", "采样"),
    ("perf", "性能"),
    ("cache", "缓存"),
    ("server", "服务"),
    ("extra", "扩展"),
    ("cli", "CLI"),
)
GROUP_LABELS = dict(GROUPS)

_CACHE_TYPES = ("", "f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1")

# ---------------- 常用参数（常驻主界面） ----------------
MAIN_PARAMS = (
    P("host", "--host", "绑定地址", "127.0.0.1", "main", cli=False),
    P("port", "--port", "端口", "8080", "main", cli=False),
    P("ngl", "-ngl", "GPU 层数", "99", "main"),
    P("ctx", "-c", "上下文长度", "0 = 从模型读取", "main"),
    P("threads", "-t", "CPU 线程数", "默认 = 物理核心数", "main"),
    P("fa", "-fa", "Flash Attention", "", "main", "combo", ("", "auto", "on", "off")),
    P("alias", "--alias", "模型别名", "供 /v1/models 显示", "main", cli=False),
    P("api_key", "--api-key", "API 密钥", "可选，留空不鉴权", "main", cli=False),
)

# ---------------- 采样与生成 ----------------
SAMPLING_PARAMS = (
    P("predict", "-n", "最大生成数", "-1 = 不限制", "sampling"),
    P("temp", "--temp", "温度", "默认 0.8", "sampling"),
    P("top_k", "--top-k", "Top-k", "默认 40", "sampling"),
    P("top_p", "--top-p", "Top-p", "默认 0.95", "sampling"),
    P("min_p", "--min-p", "Min-p", "默认 0.05", "sampling"),
    P("top_nsigma", "--top-nsigma", "Top-nσ", "-1 = 禁用", "sampling"),
    P("xtc_probability", "--xtc-probability", "XTC 概率", "默认 0.0", "sampling"),
    P("xtc_threshold", "--xtc-threshold", "XTC 阈值", "默认 0.1", "sampling"),
    P("typical", "--typical", "Typical-p", "默认 1.0", "sampling"),
    P("repeat_penalty", "--repeat-penalty", "重复惩罚", "默认 1.0", "sampling"),
    P("repeat_last_n", "--repeat-last-n", "重复回溯窗口", "默认 64", "sampling"),
    P("presence_penalty", "--presence-penalty", "存在惩罚", "默认 0.0", "sampling"),
    P("frequency_penalty", "--frequency-penalty", "频率惩罚", "默认 0.0", "sampling"),
    P("dry_multiplier", "--dry-multiplier", "DRY 系数", "默认 0.0", "sampling"),
    P("dry_penalty_last_n", "--dry-penalty-last-n", "DRY 回溯窗口", "默认 0", "sampling"),
    P("dynatemp_range", "--dynatemp-range", "动态温度范围", "默认 0.0", "sampling"),
    P("mirostat", "--mirostat", "Mirostat", "0 关闭 / 1 / 2", "sampling",
      "combo", ("", "0", "1", "2")),
    P("mirostat_lr", "--mirostat-lr", "Mirostat 学习率", "默认 0.1", "sampling"),
    P("mirostat_ent", "--mirostat-ent", "Mirostat 目标熵", "默认 5.0", "sampling"),
    P("samplers", "--samplers", "采样器顺序", "如 top_k;top_p;min_p;temperature", "sampling"),
    P("sampling_seq", "--sampling-seq", "采样序列", "如 kpnmdt", "sampling"),
    P("reasoning", "--reasoning", "思考模式", "", "sampling", "combo", ("", "auto", "on", "off")),
    P("seed", "-s", "随机种子", "-1 = 随机", "sampling"),
    P("logit_bias", "--logit-bias", "logit 偏置", "如 15043:1.5", "sampling"),
    P("grammar_file", "--grammar-file", "语法文件", "GBNF 约束输出", "sampling", "file"),
    P("json_schema_file", "--json-schema-file", "JSON Schema 文件", "JSON 结构化输出", "sampling", "file"),
    P("ignore_eos", "--ignore-eos", "忽略 EOS", "不因结束符停止", "sampling", "bool"),
)

# ---------------- 性能与硬件 ----------------
PERF_PARAMS = (
    P("batch", "-b", "逻辑批大小", "默认 2048", "perf"),
    P("ubatch", "-ub", "物理批大小", "默认 512", "perf"),
    P("threads_batch", "-tb", "批处理线程数", "默认同 -t", "perf"),
    P("keep", "--keep", "保留 prompt tokens", "默认 0", "perf"),
    P("split_mode", "-sm", "多 GPU 切分", "", "perf", "combo", ("", "none", "layer", "row", "tensor")),
    P("main_gpu", "-mg", "主 GPU 索引", "默认 0", "perf"),
    P("tensor_split", "-ts", "张量切分比例", "逗号分隔，如 0.5,0.5", "perf"),
    P("device", "-dev", "后端设备", "如 CUDA0 / CPU", "perf"),
    P("prio", "--prio", "线程优先级", "", "perf", "combo", ("", "-1", "0", "1", "2", "3")),
    P("poll", "--poll", "轮询等级", "0 - 100，默认 50", "perf"),
    P("cpu_mask", "-C", "CPU 亲和掩码", "十六进制", "perf"),
    P("cpu_range", "-Cr", "CPU 范围", "如 0-15", "perf"),
    P("numa", "--numa", "NUMA 策略", "", "perf", "combo", ("", "distribute", "isolate")),
    P("load_mode", "-lm", "模型加载模式", "", "perf", "combo",
      ("", "auto", "none", "mmap", "mlock", "mmap+mlock")),
    P("rpc", "--rpc", "RPC 服务器", "逗号分隔 host:port", "perf"),
    P("override_kv", "--override-kv", "覆盖模型元数据", "KEY=VAL", "perf"),
    P("override_tensor", "-ot", "覆盖张量后端", "正则=设备", "perf"),
    P("no_repack", "-nr", "禁用权重重打包", "关闭 repack 优化", "perf", "bool"),
    P("skip_warmup", "--no-warmup", "跳过预热", "默认预热", "perf", "bool"),
    P("verbose", "-v", "详细日志", "输出更多调试信息", "perf", "bool"),
    P("log_verbosity", "-lv", "日志详细级别", "数值越大越详细", "perf"),
    P("log_file", "--log-file", "日志文件", "写入指定文件", "perf", "file"),
    P("log_disable", "--log-disable", "禁用日志", "完全关闭日志输出", "perf", "bool"),
    P("offline", "--offline", "离线模式", "禁止联网拉取模型", "perf", "bool"),
)

# ---------------- 上下文与 KV 缓存 ----------------
CACHE_PARAMS = (
    P("cache_type_k", "-ctk", "K 缓存类型", "", "cache", "combo", _CACHE_TYPES),
    P("cache_type_v", "-ctv", "V 缓存类型", "", "cache", "combo", _CACHE_TYPES),
    P("no_kv_offload", "-nkvo", "禁用 KV 卸载", "KV 留在主内存", "cache", "bool"),
    P("swa_full", "--swa-full", "全尺寸 SWA 缓存", "默认关闭", "cache", "bool"),
    P("defrag_thold", "-dt", "碎片整理阈值", "已标记弃用", "cache"),
    P("cache_ram", "-cram", "缓存 RAM 容量", "单位 MB", "cache"),
    P("ctx_checkpoints", "-ctxcp", "上下文检查点数", "默认 0", "cache"),
    P("rope_scaling", "--rope-scaling", "RoPE 缩放", "", "cache", "combo",
      ("", "none", "linear", "yarn")),
    P("rope_freq_base", "--rope-freq-base", "RoPE 基频", "默认 0 = 模型值", "cache"),
    P("rope_freq_scale", "--rope-freq-scale", "RoPE 频率缩放", "默认 0 = 模型值", "cache"),
    P("yarn_orig_ctx", "--yarn-orig-ctx", "YaRN 原始上下文", "默认 0", "cache"),
    P("yarn_ext_factor", "--yarn-ext-factor", "YaRN 外推因子", "默认 -1", "cache"),
    P("yarn_attn_factor", "--yarn-attn-factor", "YaRN 注意力因子", "默认 1.0", "cache"),
    P("no_context_shift", "--no-context-shift", "禁用上下文移位", "上下文满时直接报错", "cache", "bool"),
    P("cache_reuse", "--cache-reuse", "缓存复用块大小", "默认 0", "cache", cli=False),
    P("kv_unified", "-kvu", "统一 KV 缓存", "所有 slot 共享 KV", "cache", "bool", cli=False),
    P("no_cache_prompt", "--no-cache-prompt", "禁用提示缓存", "默认启用", "cache", "bool", cli=False),
)

# ---------------- 服务 / HTTP API（仅 llama-server） ----------------
SERVER_PARAMS = (
    P("nparallel", "-np", "并行 slot 数", "默认 1", "server", cli=False),
    P("no_cont_batching", "-nocb", "禁用连续批处理", "默认启用", "server", "bool", cli=False),
    P("reasoning_format", "--reasoning-format", "思考输出格式", "", "server", "combo",
      ("", "none", "deepseek", "deepseek-legacy"), cli=False),
    P("reasoning_effort", "--reasoning-effort", "思考力度", "", "server", "combo",
      ("", "default", "minimal", "low", "medium", "high", "xhigh"), cli=False),
    P("reasoning_budget", "--reasoning-budget", "思考预算", "-1 = 不限制", "server", cli=False),
    P("no_jinja", "--no-jinja", "禁用 Jinja 模板", "默认启用", "server", "bool", cli=False),
    P("chat_template", "--chat-template", "内置对话模板", "如 chatml / llama3", "server", cli=False),
    P("chat_template_file", "--chat-template-file", "对话模板文件", "自定义 Jinja 模板", "server", "file", cli=False),
    P("chat_template_kwargs", "--chat-template-kwargs", "模板参数 JSON", '如 {"enable_thinking":false}', "server", cli=False),
    P("skip_chat_parsing", "--skip-chat-parsing", "跳过对话解析", "原样传递 messages", "server", "bool", cli=False),
    P("api_key_file", "--api-key-file", "API 密钥文件", "从文件读取密钥", "server", "file", cli=False),
    P("ssl_key", "--ssl-key-file", "SSL 私钥", "启用 HTTPS", "server", "file", cli=False),
    P("ssl_cert", "--ssl-cert-file", "SSL 证书", "启用 HTTPS", "server", "file", cli=False),
    P("static_path", "--path", "静态文件目录", "自定义 WebUI 资源", "server", "dir", cli=False),
    P("api_prefix", "--api-prefix", "API 路径前缀", "不含结尾斜杠", "server", cli=False),
    P("timeout", "-to", "请求超时", "单位秒，默认 600", "server", cli=False),
    P("threads_http", "--threads-http", "HTTP 线程数", "-1 = 自动", "server", cli=False),
    P("sse_ping_interval", "--sse-ping-interval", "SSE 心跳间隔", "单位秒", "server", cli=False),
    P("cors_origins", "--cors-origins", "CORS 来源", "逗号分隔，默认 *", "server", cli=False),
    P("slot_save_path", "--slot-save-path", "slot 缓存目录", "保存 KV cache", "server", "dir", cli=False),
    P("models_dir", "--models-dir", "路由模型目录", "router 模式", "server", "dir", cli=False),
    P("models_max", "--models-max", "路由最大模型数", "默认 4，0 = 无限", "server", cli=False),
    P("pooling", "--pooling", "池化方式", "", "server", "combo",
      ("", "none", "mean", "cls", "last", "rank"), cli=False),
    P("metrics", "--metrics", "Prometheus 指标", "暴露 /metrics", "server", "bool", cli=False),
    P("props", "--props", "允许修改全局属性", "开放 POST /props", "server", "bool", cli=False),
    P("no_slots", "--no-slots", "关闭 slots 端点", "默认启用", "server", "bool", cli=False),
    P("embedding", "--embedding", "嵌入模式", "仅用于嵌入模型", "server", "bool", cli=False),
    P("reranking", "--reranking", "重排序端点", "启用 rerank", "server", "bool", cli=False),
    P("reuse_port", "--reuse-port", "端口复用", "多进程共享端口", "server", "bool", cli=False),
    P("no_webui", "--no-webui", "关闭内置 WebUI", "仅保留 API", "server", "bool", cli=False),
)

# ---------------- 扩展 / 多模态 / 投机解码 ----------------
EXTRA_PARAMS = (
    P("lora", "--lora", "LoRA 适配器", ".gguf 文件", "extra", "file"),
    P("control_vector", "--control-vector", "控制向量", ".gguf 文件", "extra", "file"),
    P("mmproj", "-mm", "多模态投影器", "mmproj-*.gguf", "extra", "file"),
    P("model_draft", "-md", "草稿模型", "投机解码用小模型", "extra", "file"),
    P("draft_max", "--draft-max", "草稿最大 token", "默认 16", "extra"),
    P("draft_min", "--draft-min", "草稿最小 token", "默认 0", "extra"),
    P("image_min_tokens", "--image-min-tokens", "图像最小 token", "视觉模型", "extra"),
    P("image_max_tokens", "--image-max-tokens", "图像最大 token", "视觉模型", "extra"),
    P("video_fps", "--video-fps", "视频采样帧率", "视觉模型", "extra"),
    P("no_perf", "--no-perf", "关闭性能统计", "启用后无法解析 tok/s", "extra", "bool"),
)

# ---------------- CLI 专属 ----------------
CLI_PARAMS = (
    P("cli_system_prompt", "-sys", "CLI 系统提示词", "直连模式的 system prompt", "cli", server=False),
    P("cli_system_prompt_file", "-sysf", "系统提示词文件", "从文件读取", "cli", "file", server=False),
    P("cli_prompt_file", "-f", "初始提示词文件", "启动后立即输入", "cli", "file", server=False),
    P("cli_output_file", "-o", "输出文件", "同时写入文件", "cli", "file", server=False),
    P("cli_reverse_prompt", "-r", "反向提示词", "遇到该文本暂停", "cli", server=False),
    P("single_turn", "-st", "单轮模式", "回答一次后退出", "cli", "bool", server=False),
    P("multiline_input", "-mli", "多行输入", "反斜杠续行", "cli", "bool", server=False),
    P("show_timings", "--show-timings", "显示耗时统计", "输出 tok/s 明细", "cli", "bool", server=False),
    P("color", "-co", "彩色输出", "终端着色", "cli", "bool", server=False),
    P("no_display_prompt", "--no-display-prompt", "不回显提示词", "精简终端输出", "cli", "bool", server=False),
    P("simple_io", "--simple-io", "简易 IO", "去掉交互提示符", "cli", "bool", server=False),
)

OTHER_PARAMS = (SAMPLING_PARAMS + PERF_PARAMS + CACHE_PARAMS +
                SERVER_PARAMS + EXTRA_PARAMS + CLI_PARAMS)
ALL_PARAMS = MAIN_PARAMS + OTHER_PARAMS
ADV_PARAMS = OTHER_PARAMS  # 兼容旧引用
PARAM_BY_KEY = {p.key: p for p in ALL_PARAMS}


def params_for_group(group: str) -> tuple:
    if group == "all":
        return OTHER_PARAMS
    return tuple(p for p in OTHER_PARAMS if p.group == group)


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
    """兼容两种 llama.cpp 速率日志。"""
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
            return False, "请先设置程序路径（服务页 → llama.cpp 目录）"
        if not path.is_file():
            return False, f"程序路径不存在：\n{program}"

        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
