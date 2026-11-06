# -*- coding: utf-8 -*-
"""构建 LlamaGUI.exe / uninstall.exe 以及带自定义图标的运行时解释器。

v0.0.3 图标链路（解决任务管理器 / 任务栏显示 Python 原生图标的问题）：

1. exe 文件图标：启动器模板(w64/w32.exe) 自身带有 RT_GROUP_ICON=101 的
   Python 资源组，旧版只额外写入 id=1，导致一个 exe 里存在两组互相冲突的
   图标元数据。这里先删除全部 RT_ICON / RT_GROUP_ICON 资源，再写入唯一一组。
2. 运行时进程图标：启动器通过 shebang 唤起解释器，任务管理器、任务栏、
   Alt-Tab 显示的是「解释器进程」的图标，而不是 LlamaGUI.exe 的图标。
   因此把 .venv\\Scripts\\pythonw.exe 复制为 LlamaRuntime.exe 并注入同一套
   图标，shebang 指向该副本。进程名与图标都不再是 Python。
3. 窗口与托盘图标：由 Qt 在运行时从 assets/app.ico 加载，见 main.py / app/tray.py。

exe 只是「薄启动器」，不是把应用打包进去的单文件程序；应用代码始终是本目录
的 main.py + app/，由本目录虚拟环境运行。全部路径相对程序目录，换电脑后由
first_run.bat 重建即可（包括运行时图标副本），不依赖任何绝对路径。

用法：python tools/build_launchers.py
"""
from __future__ import annotations

import ctypes
import io
import os
import shutil
import struct
import sys
import zipfile
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
STUBS = Path(__file__).resolve().parent / "launcher"
VENV_SCRIPTS = ROOT / ".venv" / "Scripts"
RUNTIME_REL = ".venv\\Scripts\\LlamaRuntime.exe"
SHEBANG = ("#!" + RUNTIME_REL + "\n").encode("ascii")
MAX_SIZE = 1024 * 1024
APP_ID = "LlamaStudio.App.4"
LANG = 0x409
RT_ICON = 3
RT_GROUP_ICON = 14

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
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LlamaStudio.App.4")
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
    """清理已装依赖与缓存；保留 pyvenv.cfg 与最小解释器骨架。

    卸载程序自身的解释器就来自 .venv，若整个删除，之后将无法再次运行卸载。
    保留 pyvenv.cfg / pythonw.exe / LlamaRuntime.exe 可保证卸载程序始终可用；
    重装时 first_run.bat 检测到 Scripts\\python.exe 不存在会自动重建完整环境。
    """
    venv = root / ".venv"
    keep = {"pythonw.exe", "llamaruntime.exe"}
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
                if child.name.lower() in keep:
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
    """延迟删除：启动器运行时会占用 .venv\\Scripts\\LlamaRuntime.exe，需等本进程退出。"""
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


# ---------------------------------------------------------------- Win32 资源 API
def _kernel32():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    k32.BeginUpdateResourceW.restype = wintypes.HANDLE
    k32.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                    wintypes.WORD, ctypes.c_void_p, wintypes.DWORD]
    k32.UpdateResourceW.restype = wintypes.BOOL
    k32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    k32.EndUpdateResourceW.restype = wintypes.BOOL
    k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    k32.LoadLibraryExW.restype = wintypes.HMODULE
    k32.FreeLibrary.argtypes = [wintypes.HMODULE]
    k32.EnumResourceNamesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_long]
    k32.EnumResourceNamesW.restype = wintypes.BOOL
    k32.EnumResourceLanguagesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
    k32.EnumResourceLanguagesW.restype = wintypes.BOOL
    k32.FindResourceW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p]
    k32.FindResourceW.restype = wintypes.HRSRC
    k32.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    k32.LoadResource.restype = wintypes.HGLOBAL
    k32.LockResource.argtypes = [wintypes.HGLOBAL]
    k32.LockResource.restype = ctypes.c_void_p
    k32.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    k32.SizeofResource.restype = wintypes.DWORD
    return k32


NAME_CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_long)
LANG_CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.WORD, ctypes.c_long)


def _parse_ico(path: Path):
    raw = path.read_bytes()
    _reserved, _type, count = struct.unpack_from("<HHH", raw, 0)
    entries, images = [], []
    for i in range(count):
        w, h, cc, res, planes, bitcount, size, offset = struct.unpack_from(
            "<BBBBHHII", raw, 6 + i * 16)
        entries.append((w, h, cc, res, planes, bitcount, size))
        images.append(raw[offset:offset + size])
    group = bytearray(struct.pack("<HHH", 0, 1, count))
    for idx, e in enumerate(entries, 1):
        group += struct.pack("<BBBBHHIH", e[0], e[1], e[2], e[3], e[4], e[5], e[6], idx)
    return images, bytes(group)


def _icon_signature(path: Path) -> tuple[list[int], list[int]]:
    """读取 PE 中现有的图标资源 ID（用于判断是否已注入过）。"""
    k32 = _kernel32()
    module = k32.LoadLibraryExW(str(path), None, 0x2)
    if not module:
        return [], []
    try:
        result = []
        for rtype in (RT_ICON, RT_GROUP_ICON):
            names: list[int] = []
            cb = NAME_CB(lambda _m, _t, n, _l, out=names: (out.append(int(n)), True)[1])
            k32.EnumResourceNamesW(module, ctypes.c_void_p(rtype), cb, 0)
            result.append(names)
        return result[0], result[1]
    finally:
        k32.FreeLibrary(module)


def _existing_icon_resources(k32, path: Path):
    """在原始 PE 上枚举全部 (类型, ID, 语言)，供 BeginUpdateResource 删除。"""
    module = k32.LoadLibraryExW(str(path), None, 0x2)
    if not module:
        return []
    found = []
    try:
        for rtype in (RT_ICON, RT_GROUP_ICON):
            names: list[int] = []
            cb = NAME_CB(lambda _m, _t, n, _l, out=names: (out.append(int(n)), True)[1])
            k32.EnumResourceNamesW(module, ctypes.c_void_p(rtype), cb, 0)
            for name in names:
                langs: list[int] = []
                lcb = LANG_CB(lambda _m, _t, _n, lang, _l, out=langs: (out.append(int(lang)), True)[1])
                k32.EnumResourceLanguagesW(module, ctypes.c_void_p(rtype),
                                           ctypes.c_void_p(name), lcb, 0)
                for lang in langs:
                    found.append((rtype, name, lang))
    finally:
        k32.FreeLibrary(module)
    return found


def _set_icon(exe: Path, ico: Path) -> None:
    """清空原有图标资源后写入唯一一组自定义图标，避免多组资源互相干扰。"""
    if sys.platform != "win32":
        return
    images, group = _parse_ico(ico)
    k32 = _kernel32()
    stale = _existing_icon_resources(k32, exe)
    handle = k32.BeginUpdateResourceW(str(exe), False)
    if not handle:
        raise OSError("BeginUpdateResourceW 失败: %s" % ctypes.get_last_error())
    buffers = []
    try:
        for rtype, name, lang in stale:
            k32.UpdateResourceW(handle, ctypes.c_void_p(rtype), ctypes.c_void_p(name),
                                lang, None, 0)
        for idx, data in enumerate(images, 1):
            buf = ctypes.create_string_buffer(data)
            buffers.append(buf)
            if not k32.UpdateResourceW(handle, ctypes.c_void_p(RT_ICON), ctypes.c_void_p(idx),
                                       LANG, buf, len(data)):
                raise OSError("RT_ICON 写入失败: %s" % ctypes.get_last_error())
        buf = ctypes.create_string_buffer(group)
        buffers.append(buf)
        if not k32.UpdateResourceW(handle, ctypes.c_void_p(RT_GROUP_ICON), ctypes.c_void_p(1),
                                   LANG, buf, len(group)):
            raise OSError("RT_GROUP_ICON 写入失败: %s" % ctypes.get_last_error())
    finally:
        if not k32.EndUpdateResourceW(handle, False):
            raise OSError("EndUpdateResourceW 失败: %s" % ctypes.get_last_error())


def build_runtime(ico: Path) -> Path:
    """复制 pythonw.exe 并注入图标：任务管理器中的进程图标由此决定。"""
    source = VENV_SCRIPTS / "pythonw.exe"
    target = VENV_SCRIPTS / "LlamaRuntime.exe"
    icons, groups = _icon_signature(target) if target.is_file() else ([], [])
    if groups == [1] and len(icons) == len(_parse_ico(ico)[0]):
        return target                       # 已注入，且可能正在被占用，直接复用
    if not source.is_file():
        raise FileNotFoundError(
            "缺少 %s，请先运行 first_run.bat 创建虚拟环境" % source)
    shutil.copyfile(str(source), str(target))
    _set_icon(target, ico)
    return target


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


def verify(path: Path, expected_icons: int) -> tuple[int, bool]:
    size = path.stat().st_size
    data = path.read_bytes()
    has_payload = SHEBANG in data and b"PK\x05\x06" in data[-64:]
    icons, groups = _icon_signature(path)
    ok = has_payload and groups == [1] and len(icons) == expected_icons
    return size, ok


def main() -> None:
    print("App directory:", ROOT)
    print("Interpreter:", struct.calcsize("P") * 8, "bit")
    app_ico = ASSETS / "app.ico"
    expected = len(_parse_ico(app_ico)[0])

    runtime = build_runtime(app_ico)
    icons, groups = _icon_signature(runtime)
    print("  %-16s %7d bytes  RT_ICON=%d RT_GROUP_ICON=%s  verify=%s" %
          (runtime.name, runtime.stat().st_size, len(icons), groups,
           "OK" if groups == [1] and len(icons) == expected else "FAILED"))
    if groups != [1] or len(icons) != expected:
        raise SystemExit(1)

    targets = (
        ("LlamaGUI.exe", app_ico, APP_BOOTSTRAP),
        ("uninstall.exe", ASSETS / "uninstall.ico", UNINSTALL_BOOTSTRAP),
    )
    for name, ico, source in targets:
        path = build(name, ico, source)
        size, ok = verify(path, expected)
        print("  %-16s %7d bytes  <1MB=%s  verify=%s" %
              (name, size, size < MAX_SIZE, "OK" if ok else "FAILED"))
        if not ok or size >= MAX_SIZE:
            raise SystemExit(1)
    print("Done. shebang -> %s (relative, rebuilt by first_run.bat)" % RUNTIME_REL)


if __name__ == "__main__":
    main()
