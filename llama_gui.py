# -*- coding: utf-8 -*-
"""
llama.cpp GUI - 简单图形界面启动 llama-server / llama-cli
"""
import sys
import json
import subprocess
import threading
import queue
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QPushButton, QComboBox, QFileDialog,
    QPlainTextEdit, QMessageBox, QCheckBox
)

CONFIG_NAME = "llama_gui_config.json"


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


class LlamaGui(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("llama.cpp GUI")
        self.resize(940, 720)

        self.process = None                # subprocess.Popen 对象
        self.reader_thread = None
        self.output_queue = queue.Queue()
        self.config_path = get_base_dir() / CONFIG_NAME
        self.config = self._load_config()
        self._last_program_type = "llama-server"

        # 输出轮询定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._process_output_queue)

        self._build_ui()
        self._load_config_to_ui()
        self._update_buttons()

    # ---------------- 配置持久化 ----------------
    def _load_config(self) -> dict:
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"读取配置失败: {e}")
        return {}

    def _save_config(self):
        try:
            self._collect_config_from_ui()
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def _collect_config_from_ui(self):
        c = self.config
        pt = self.program_type_combo.currentText()
        c["program_type"] = pt
        c[f"path_{pt}"] = self.path_edit.text()
        c["scan_dir"] = self.scan_dir_edit.text()
        c["model"] = self.model_combo.currentText().strip()
        c["host"] = self.host_edit.text()
        c["port"] = self.port_edit.text()
        c["ngl"] = self.ngl_edit.text()
        c["ctx"] = self.ctx_edit.text()
        c["threads"] = self.threads_edit.text()
        c["batch"] = self.batch_edit.text()
        c["ubatch"] = self.ubatch_edit.text()
        c["fa"] = self.fa_combo.currentText()
        c["predict"] = self.predict_edit.text()
        c["temp"] = self.temp_edit.text()
        c["top_p"] = self.top_p_edit.text()
        c["top_k"] = self.top_k_edit.text()
        c["seed"] = self.seed_edit.text()
        c["reasoning"] = self.reasoning_combo.currentText()
        c["nparallel"] = self.nparallel_edit.text()
        c["api_key"] = self.api_key_edit.text()
        c["alias"] = self.alias_edit.text()
        c["ssl_key"] = self.ssl_key_edit.text()
        c["ssl_cert"] = self.ssl_cert_edit.text()
        c["no_mmap"] = self.no_mmap_check.isChecked()
        c["verbose"] = self.verbose_check.isChecked()
        c["custom"] = self.custom_edit.text()

    def _load_config_to_ui(self):
        c = self.config

        self.program_type_combo.blockSignals(True)
        pt = c.get("program_type", "llama-server")
        if pt in ("llama-server", "llama-cli"):
            self.program_type_combo.setCurrentText(pt)
        self.program_type_combo.blockSignals(False)
        self._last_program_type = self.program_type_combo.currentText()

        self.path_edit.setText(c.get(f"path_{self._last_program_type}", ""))

        self.scan_dir_edit.setText(c.get("scan_dir", ""))
        if self.scan_dir_edit.text():
            self._scan_models(silent=True)

        m = c.get("model", "")
        if m:
            idx = self.model_combo.findText(m)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            else:
                self.model_combo.setCurrentText(m)

        self.host_edit.setText(c.get("host", "127.0.0.1"))
        self.port_edit.setText(c.get("port", "8080"))
        self.ngl_edit.setText(c.get("ngl", "99"))

        self.ctx_edit.setText(c.get("ctx", ""))
        self.threads_edit.setText(c.get("threads", ""))
        self.batch_edit.setText(c.get("batch", ""))
        self.ubatch_edit.setText(c.get("ubatch", ""))
        fa = c.get("fa", "auto")
        if fa not in ("", "auto", "on", "off"):
            fa = "auto"
        self.fa_combo.setCurrentText(fa)
        self.predict_edit.setText(c.get("predict", ""))
        self.temp_edit.setText(c.get("temp", ""))
        self.top_p_edit.setText(c.get("top_p", ""))
        self.top_k_edit.setText(c.get("top_k", ""))
        self.seed_edit.setText(c.get("seed", ""))

        rea = c.get("reasoning", "auto")
        if rea not in ("", "auto", "on", "off"):
            rea = "auto"
        self.reasoning_combo.setCurrentText(rea)

        self.nparallel_edit.setText(c.get("nparallel", ""))
        self.api_key_edit.setText(c.get("api_key", ""))
        self.alias_edit.setText(c.get("alias", ""))
        self.ssl_key_edit.setText(c.get("ssl_key", ""))
        self.ssl_cert_edit.setText(c.get("ssl_cert", ""))
        self.no_mmap_check.setChecked(c.get("no_mmap", False))
        self.verbose_check.setChecked(c.get("verbose", False))
        self.custom_edit.setText(c.get("custom", ""))

    # ---------------- UI 构建 ----------------
    def _wrap(self, layout) -> QWidget:
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_basic_tab(), "基础配置")
        self.tabs.addTab(self._build_perf_tab(), "性能参数")
        self.tabs.addTab(self._build_adv_tab(), "高级参数")
        root.addWidget(self.tabs)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("启动")
        self.stop_btn = QPushButton("停止")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        root.addWidget(QLabel("日志输出:"))
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 9))
        root.addWidget(self.log_edit, 1)

        stdin_row = QHBoxLayout()
        stdin_row.addWidget(QLabel("标准输入:"))
        self.stdin_edit = QLineEdit()
        self.stdin_edit.setPlaceholderText("llama-cli 交互输入（回车发送）")
        self.stdin_edit.returnPressed.connect(self._on_send_stdin)
        stdin_row.addWidget(self.stdin_edit, 1)
        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self._on_send_stdin)
        stdin_row.addWidget(send_btn)
        root.addLayout(stdin_row)

    def _build_basic_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.program_type_combo = QComboBox()
        self.program_type_combo.addItems(["llama-server", "llama-cli"])
        self.program_type_combo.currentTextChanged.connect(self._on_program_type_changed)
        form.addRow("程序类型:", self.program_type_combo)

        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("llama-server.exe 或 llama-cli.exe 的完整路径")
        b = QPushButton("浏览...")
        b.clicked.connect(self._browse_program)
        row.addWidget(self.path_edit, 1)
        row.addWidget(b)
        form.addRow("程序路径:", self._wrap(row))

        row = QHBoxLayout()
        self.scan_dir_edit = QLineEdit()
        self.scan_dir_edit.setPlaceholderText("存放 .gguf 模型的文件夹")
        b = QPushButton("浏览...")
        b.clicked.connect(self._browse_scan_dir)
        sb = QPushButton("扫描")
        sb.clicked.connect(lambda: self._scan_models(silent=False))
        row.addWidget(self.scan_dir_edit, 1)
        row.addWidget(b)
        row.addWidget(sb)
        form.addRow("模型扫描目录:", self._wrap(row))

        row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        b = QPushButton("浏览...")
        b.clicked.connect(self._browse_model)
        row.addWidget(self.model_combo, 1)
        row.addWidget(b)
        form.addRow("模型文件 (-m):", self._wrap(row))

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("127.0.0.1")
        form.addRow("绑定地址 (--host):", self.host_edit)

        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("8080")
        form.addRow("端口 (--port):", self.port_edit)

        self.ngl_edit = QLineEdit()
        self.ngl_edit.setPlaceholderText("99")
        form.addRow("GPU 层数 (-ngl):", self.ngl_edit)

        return w

    def _build_perf_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.ctx_edit = QLineEdit()
        self.ctx_edit.setPlaceholderText("默认 0（从模型加载）")
        form.addRow("上下文长度 (-c):", self.ctx_edit)

        self.threads_edit = QLineEdit()
        self.threads_edit.setPlaceholderText("默认 CPU 核数")
        form.addRow("线程数 (-t):", self.threads_edit)

        self.batch_edit = QLineEdit()
        self.batch_edit.setPlaceholderText("默认 2048")
        form.addRow("逻辑批大小 (-b):", self.batch_edit)

        self.ubatch_edit = QLineEdit()
        self.ubatch_edit.setPlaceholderText("默认 512")
        form.addRow("物理批大小 (-ub):", self.ubatch_edit)

        self.fa_combo = QComboBox()
        self.fa_combo.addItems(["", "auto", "on", "off"])
        self.fa_combo.setCurrentText("auto")
        form.addRow("Flash Attention (-fa):", self.fa_combo)

        self.predict_edit = QLineEdit()
        self.predict_edit.setPlaceholderText("默认 -1（无限）")
        form.addRow("最大生成数 (-n):", self.predict_edit)

        self.temp_edit = QLineEdit()
        self.temp_edit.setPlaceholderText("默认 0.8")
        form.addRow("温度 (--temp):", self.temp_edit)

        self.top_p_edit = QLineEdit()
        self.top_p_edit.setPlaceholderText("默认 0.95")
        form.addRow("Top-p (--top-p):", self.top_p_edit)

        self.top_k_edit = QLineEdit()
        self.top_k_edit.setPlaceholderText("默认 40")
        form.addRow("Top-k (--top-k):", self.top_k_edit)

        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("默认 -1（随机）")
        form.addRow("随机种子 (-s):", self.seed_edit)

        return w

    def _build_adv_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.reasoning_combo = QComboBox()
        self.reasoning_combo.addItems(["", "auto", "on", "off"])
        self.reasoning_combo.setCurrentText("auto")
        form.addRow("思考模式 (--reasoning):", self.reasoning_combo)

        self.nparallel_edit = QLineEdit()
        self.nparallel_edit.setPlaceholderText("默认 1")
        form.addRow("并行 slot 数 (-np):", self.nparallel_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("可选")
        form.addRow("API 密钥 (--api-key):", self.api_key_edit)

        self.alias_edit = QLineEdit()
        self.alias_edit.setPlaceholderText("可选")
        form.addRow("模型别名 (--alias):", self.alias_edit)

        row = QHBoxLayout()
        self.ssl_key_edit = QLineEdit()
        b = QPushButton("浏览...")
        b.clicked.connect(lambda: self._browse_file(self.ssl_key_edit))
        row.addWidget(self.ssl_key_edit, 1)
        row.addWidget(b)
        form.addRow("SSL 私钥 (--ssl-key-file):", self._wrap(row))

        row = QHBoxLayout()
        self.ssl_cert_edit = QLineEdit()
        b = QPushButton("浏览...")
        b.clicked.connect(lambda: self._browse_file(self.ssl_cert_edit))
        row.addWidget(self.ssl_cert_edit, 1)
        row.addWidget(b)
        form.addRow("SSL 证书 (--ssl-cert-file):", self._wrap(row))

        self.no_mmap_check = QCheckBox("禁用内存映射 (--no-mmap)")
        form.addRow("", self.no_mmap_check)

        self.verbose_check = QCheckBox("详细日志 (-v)")
        form.addRow("", self.verbose_check)

        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("额外参数，空格分隔，直接追加到命令行末尾")
        form.addRow("自定义参数:", self.custom_edit)

        return w

    # ---------------- 文件/目录选择 ----------------
    def _browse_program(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择可执行文件", "", "可执行文件 (*.exe);;所有文件 (*)"
        )
        if p:
            self.path_edit.setText(p)

    def _browse_scan_dir(self):
        p = QFileDialog.getExistingDirectory(self, "选择模型扫描目录")
        if p:
            self.scan_dir_edit.setText(p)

    def _browse_model(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择模型文件", "", "GGUF 模型 (*.gguf);;所有文件 (*)"
        )
        if p:
            self.model_combo.setCurrentText(p)

    def _browse_file(self, edit: QLineEdit):
        p, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "所有文件 (*)")
        if p:
            edit.setText(p)

    def _on_program_type_changed(self, new_type: str):
        if self._last_program_type and self._last_program_type != new_type:
            self.config[f"path_{self._last_program_type}"] = self.path_edit.text()
        self._last_program_type = new_type
        self.path_edit.setText(self.config.get(f"path_{new_type}", ""))

    # ---------------- 扫描模型 ----------------
    def _scan_models(self, silent: bool = False):
        folder = self.scan_dir_edit.text().strip()
        if not folder or not Path(folder).is_dir():
            if not silent:
                QMessageBox.warning(self, "警告", "扫描目录不存在或无效")
            return
        current = self.model_combo.currentText().strip()
        files = sorted(Path(folder).rglob("*.gguf"))
        self.model_combo.clear()
        for f in files:
            self.model_combo.addItem(str(f))
        if current:
            idx = self.model_combo.findText(current)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            else:
                self.model_combo.setCurrentText(current)
        if not silent:
            self._append_log(f"[扫描] 在 {folder} 中找到 {len(files)} 个 .gguf 文件\n")

    # ---------------- 日志 ----------------
    def _append_log(self, text: str):
        self.log_edit.moveCursor(QTextCursor.End)
        self.log_edit.insertPlainText(text)
        self.log_edit.moveCursor(QTextCursor.End)

    # ---------------- 参数拼装 ----------------
    def _build_args(self) -> list:
        args = []
        m = self.model_combo.currentText().strip()
        if m:
            args += ["-m", m]
        host = self.host_edit.text().strip()
        if host:
            args += ["--host", host]
        port = self.port_edit.text().strip()
        if port:
            args += ["--port", port]
        ngl = self.ngl_edit.text().strip()
        if ngl:
            args += ["-ngl", ngl]

        # Tab2
        for edit, flag in [
            (self.ctx_edit, "-c"),
            (self.threads_edit, "-t"),
            (self.batch_edit, "-b"),
            (self.ubatch_edit, "-ub"),
            (self.predict_edit, "-n"),
            (self.temp_edit, "--temp"),
            (self.top_p_edit, "--top-p"),
            (self.top_k_edit, "--top-k"),
            (self.seed_edit, "-s"),
        ]:
            v = edit.text().strip()
            if v:
                args += [flag, v]

        fa = self.fa_combo.currentText().strip()
        if fa:
            args += ["-fa", fa]

        # Tab3
        reasoning = self.reasoning_combo.currentText().strip()
        if reasoning:
            args += ["--reasoning", reasoning]

        for edit, flag in [
            (self.nparallel_edit, "-np"),
            (self.api_key_edit, "--api-key"),
            (self.alias_edit, "--alias"),
            (self.ssl_key_edit, "--ssl-key-file"),
            (self.ssl_cert_edit, "--ssl-cert-file"),
        ]:
            v = edit.text().strip()
            if v:
                args += [flag, v]

        if self.no_mmap_check.isChecked():
            args.append("--no-mmap")
        if self.verbose_check.isChecked():
            args.append("-v")

        custom = self.custom_edit.text().strip()
        if custom:
            args += custom.split()

        return args

    # ---------------- 进程管理 ----------------
    def _on_start(self):
        program = self.path_edit.text().strip()
        if not program:
            QMessageBox.warning(self, "警告", "请先设置程序路径")
            return
        if not Path(program).exists():
            QMessageBox.warning(self, "警告", f"程序路径不存在：\n{program}")
            return

        args = self._build_args()
        self.log_edit.clear()

        # Windows 下隐藏控制台窗口
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self.process = subprocess.Popen(
                [program] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                creationflags=creationflags,
                bufsize=0,
                universal_newlines=False,
            )
        except Exception as e:
            self._append_log(f"[启动失败] {e}\n")
            self.process = None
            self._update_buttons()
            return

        # 打印命令行
        cmd_preview = " ".join([f'"{program}"'] + [
            f'"{a}"' if " " in a else a for a in args
        ])
        self._append_log(f"$ {cmd_preview}\n\n")

        # 启动输出读取线程
        self.output_queue = queue.Queue()
        self.reader_thread = threading.Thread(
            target=self._read_output, daemon=True
        )
        self.reader_thread.start()

        # 启动轮询定时器
        self.timer.start(100)
        self._update_buttons()

    def _read_output(self):
        """在线程中读取子进程输出，放入队列"""
        try:
            while True:
                line = self.process.stdout.readline()
                if not line:
                    break
                self.output_queue.put(line)
        except Exception:
            pass
        finally:
            self.output_queue.put(None)  # 结束标志

    def _process_output_queue(self):
        """在主线程中处理输出队列（由 QTimer 调用）"""
        while True:
            try:
                line = self.output_queue.get_nowait()
            except queue.Empty:
                break

            if line is None:
                # 输出流结束，进程即将退出
                self.timer.stop()
                self._on_process_finished()
                return

            text = line.decode("utf-8", errors="replace")
            self._append_log(text)

    def _on_process_finished(self):
        exit_code = self.process.returncode if self.process else None
        self._append_log(f"\n[进程结束] 退出码={exit_code}\n")
        self.process = None
        self.reader_thread = None
        self._update_buttons()

    def _on_stop(self):
        if self.process and self.process.poll() is None:
            self._append_log("\n[停止中...]\n")
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._append_log("[超时，强制结束]\n")
                self.process.kill()
                self.process.wait()
            self.timer.stop()
            self._on_process_finished()
        else:
            self._update_buttons()

    def _on_send_stdin(self):
        text = self.stdin_edit.text()
        if not text:
            return
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.write((text + "\n").encode("utf-8"))
                self.process.stdin.flush()
                self._append_log(f"> {text}\n")
                self.stdin_edit.clear()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"写入标准输入失败：{e}")
        else:
            QMessageBox.information(self, "提示", "进程未在运行")

    def _update_buttons(self):
        running = self.process is not None and self.process.poll() is None
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.statusBar().showMessage("运行中" if running else "就绪")

    # ---------------- 关闭 ----------------
    def closeEvent(self, event):
        self._save_config()
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        self.timer.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("llama.cpp GUI")
    w = LlamaGui()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()