# -*- coding: utf-8 -*-
"""构建 LlamaGUI.exe / uninstall.exe（仅使用 Python 标准库，不需要编译器）。

原理：exe = pip 附带的无控制台启动器模板(w64/w32.exe)
      + 写进 PE 资源的自定义图标
      + 相对 shebang（指向本目录 .venv）
      + 内嵌 __main__.py 的 zip 载荷

因此 exe 只是「薄启动器」，不是把整个应用打包进去的单文件程序；
应用代码始终是本目录的 main.py + app/，并由本目录虚拟环境的 pythonw 运行。
全部路径相对程序目录，换电脑后由 first_run.bat 重建即可。

用法：python tools/build_launchers.py
"""
from __future__ import annotations

import ctypes
import io
import os
import struct
import sys
import zipfile
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
STUBS = Path(__file__).resolve().parent / "launcher"
SHEBANG = b"#!.venv\\Scripts\\pythonw.exe\n"   # 相对 exe 所在目录解析
MAX_SIZE = 1024 * 1024

APP_BOOTSTRAP = r'''# -*- coding: utf-8 -*-
"""LlamaGUI.exe 内嵌启动代码：用本目录 .venv 运行 main.py。"""
import os
import runpy
import sys
from pathlib import Path


def alert(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Llama Studio", 0x10)
    except Exception:
        pass


def main():
    root = Path(sys.argv[0]).resolve().parent
    script = root / "main.py"
    if not script.is_file():
        alert("未找到 main.py，请确认程序目录完整。")
        return 1
    try:
        import PySide6  # noqa: F401
    except ImportError:
        alert("虚拟环境尚未安装依赖。\n请先双击运行 first_run.bat 完成安装。")
        return 1
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LlamaStudio.App")
        except Exception:
            pass
    os.chdir(str(root))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit:
        raise
    except Exception as exc:
        alert("启动失败：\n%s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

UNINSTALL_BOOTSTRAP = r'''# -*- coding: utf-8 -*-
"""uninstall.exe 内嵌卸载代码：仅用标准库，不依赖虚拟环境。"""
import ctypes
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MB_YESNOCANCEL = 0x03
MB_ICONQUESTION = 0x20
MB_ICONERROR = 0x10
MB_ICONINFO = 0x40
MB_DEFBUTTON2 = 0x100
MB_SETFOREGROUND = 0x10000
IDYES, IDNO, IDCANCEL = 6, 7, 2


def message(text, title, flags):
    try:
        return ctypes.windll.user32.MessageBoxW(None, text, title, flags)
    except Exception:
        return IDCANCEL


def clean(root):
    """清理已装依赖与缓存；保留 pyvenv.cfg + pythonw.exe 极小骨架。

    卸载程序自身的解释器就来自 .venv，若整个删除，之后将无法再次运行卸载。
    保留这两个文件（约 260 KB）可保证卸载程序始终可用；重装时 first_run.bat
    检测到 Scripts\\python.exe 不存在会自动重建完整虚拟环境。
    """
    venv = root / ".venv"
    if venv.is_dir():
        for child in list(venv.iterdir()):
            if child.name == "pyvenv.cfg" or child.name.lower() == "scripts":
                continue
            if child.is_dir():
                shutil.rmtree(str(child), ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass
        scripts = venv / "Scripts"
        if scripts.is_dir():
            for child in list(scripts.iterdir()):
                if child.name.lower() == "pythonw.exe":
                    continue
                if child.is_dir():
                    shutil.rmtree(str(child), ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except OSError:
                        pass
    for sub in (root, root / "app", root / "tools"):
        cache = sub / "__pycache__"
        if cache.is_dir():
            shutil.rmtree(str(cache), ignore_errors=True)


def schedule_remove(target):
    """延迟删除：启动器运行时会占用 .venv\\Scripts\\pythonw.exe，需等本进程退出。"""
    literal = str(target).replace("'", "''")
    cmd = (
        "Start-Sleep -Milliseconds 1200; "
        "for ($i = 0; $i -lt 20; $i++) { "
        "Remove-Item -LiteralPath '" + literal + "' -Recurse -Force -ErrorAction SilentlyContinue; "
        "if (-not (Test-Path -LiteralPath '" + literal + "')) { break }; "
        "Start-Sleep -Milliseconds 600 }"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-Command", cmd],
            cwd=tempfile.gettempdir(), creationflags=flags,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        message("无法自动删除：\n%s\n\n请手动删除该文件夹。" % exc,
                "Llama Studio 卸载", MB_ICONERROR)


def main():
    root = Path(sys.argv[0]).resolve().parent
    if not ((root / "main.py").is_file() and (root / "first_run.bat").is_file()):
        message("目录结构不完整，已取消卸载。", "Llama Studio 卸载", MB_ICONERROR)
        return 1
    choice = message(
        "确定卸载 Llama Studio 吗？\n\n"
        "是(Y)   完整卸载：删除虚拟环境、缓存及本程序全部文件\n"
        "否(N)   仅清理环境：保留源码，之后可重新运行 first_run.bat\n"
        "取消     不做任何改动",
        "Llama Studio 卸载",
        MB_YESNOCANCEL | MB_ICONQUESTION | MB_DEFBUTTON2 | MB_SETFOREGROUND,
    )
    if choice == IDCANCEL:
        return 0
    clean(root)
    if choice == IDYES:
        message("依赖与缓存已清理。\n关闭本窗口后程序目录将自动删除。",
                "Llama Studio 卸载", MB_ICONINFO)
        schedule_remove(root)
    else:
        message("已清理虚拟环境中的依赖与缓存，程序文件已保留。\n"
                "重新运行 first_run.bat 可完整恢复；也可直接删除本文件夹完成卸载。",
                "Llama Studio 卸载", MB_ICONINFO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _kernel32():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    k32.BeginUpdateResourceW.restype = wintypes.HANDLE
    k32.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                    wintypes.WORD, ctypes.c_void_p, wintypes.DWORD]
    k32.UpdateResourceW.restype = wintypes.BOOL
    k32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    k32.EndUpdateResourceW.restype = wintypes.BOOL
    return k32


def _parse_ico(path: Path):
    raw = path.read_bytes()
    _reserved, _type, count = struct.unpack_from("<HHH", raw, 0)
    entries, images = [], []
    for i in range(count):
        w, h, cc, res, planes, bitcount, size, offset = struct.unpack_from("<BBBBHHII", raw, 6 + i * 16)
        entries.append((w, h, cc, res, planes, bitcount, size))
        images.append(raw[offset:offset + size])
    group = bytearray(struct.pack("<HHH", 0, 1, count))
    for idx, e in enumerate(entries, 1):
        group += struct.pack("<BBBBHHIH", e[0], e[1], e[2], e[3], e[4], e[5], e[6], idx)
    return images, bytes(group)


def _set_icon(exe: Path, ico: Path) -> None:
    """用 Win32 UpdateResource 把 ICO 写入 PE 的 RT_ICON / RT_GROUP_ICON。"""
    if sys.platform != "win32":
        return
    images, group = _parse_ico(ico)
    k32 = _kernel32()
    handle = k32.BeginUpdateResourceW(str(exe), False)
    if not handle:
        raise OSError("BeginUpdateResourceW 失败: %s" % ctypes.get_last_error())
    buffers = []
    try:
        for idx, data in enumerate(images, 1):
            buf = ctypes.create_string_buffer(data)
            buffers.append(buf)
            if not k32.UpdateResourceW(handle, ctypes.c_void_p(3), ctypes.c_void_p(idx),
                                       0x409, buf, len(data)):
                raise OSError("RT_ICON 写入失败: %s" % ctypes.get_last_error())
        buf = ctypes.create_string_buffer(group)
        buffers.append(buf)
        if not k32.UpdateResourceW(handle, ctypes.c_void_p(14), ctypes.c_void_p(1),
                                   0x409, buf, len(group)):
            raise OSError("RT_GROUP_ICON 写入失败: %s" % ctypes.get_last_error())
    finally:
        if not k32.EndUpdateResourceW(handle, False):
            raise OSError("EndUpdateResourceW 失败: %s" % ctypes.get_last_error())


def _zip_payload(source: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("__main__.py", source.encode("utf-8"))
    return buffer.getvalue()


def _stub_for_interpreter() -> Path:
    bits = struct.calcsize("P") * 8
    stub = STUBS / ("w%d.exe" % bits)
    if not stub.is_file():
        stub = STUBS / "w64.exe"
    return stub


def build(name: str, ico: Path, source: str) -> Path:
    stub = _stub_for_interpreter()
    if not stub.is_file():
        raise FileNotFoundError("缺少启动器模板: %s" % stub)
    if not ico.is_file():
        raise FileNotFoundError("缺少图标: %s" % ico)

    output = ROOT / name
    temp = ROOT / (name + ".tmp")
    temp.write_bytes(stub.read_bytes())
    try:
        _set_icon(temp, ico)
        with temp.open("ab") as handle:
            handle.write(SHEBANG)
            handle.write(_zip_payload(source))
        size = temp.stat().st_size
        if size >= MAX_SIZE:
            raise RuntimeError("%s 体积 %d 字节，超过 1 MB 限制" % (name, size))
        os.replace(str(temp), str(output))
    finally:
        if temp.exists():
            temp.unlink()
    return output


def verify(path: Path) -> tuple[int, bool]:
    size = path.stat().st_size
    data = path.read_bytes()
    has_payload = SHEBANG in data and b"PK\x05\x06" in data[-64:]
    has_icon = False
    if sys.platform == "win32":
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
            k32.LoadLibraryExW.restype = wintypes.HMODULE
            k32.FindResourceW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p]
            k32.FindResourceW.restype = wintypes.HRSRC
            module = k32.LoadLibraryExW(str(path), None, 0x2)
            has_icon = bool(module and k32.FindResourceW(module, ctypes.c_void_p(1), ctypes.c_void_p(14)))
        except Exception:
            pass
    return size, has_payload and (has_icon or sys.platform != "win32")


def main() -> None:
    print("程序目录:", ROOT)
    print("解释器位数:", struct.calcsize("P") * 8, "bit")
    targets = (
        ("LlamaGUI.exe", ASSETS / "app.ico", APP_BOOTSTRAP),
        ("uninstall.exe", ASSETS / "uninstall.ico", UNINSTALL_BOOTSTRAP),
    )
    for name, ico, source in targets:
        path = build(name, ico, source)
        size, ok = verify(path)
        print("  %-16s %7d bytes  <1MB=%s  校验=%s" %
              (name, size, size < MAX_SIZE, "通过" if ok else "异常"))
        if not ok or size >= MAX_SIZE:
            raise SystemExit(1)
    print("完成。启动器仅引用本目录 .venv，不含应用代码。")


if __name__ == "__main__":
    main()
