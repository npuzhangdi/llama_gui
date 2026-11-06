@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Llama Studio - 首次运行安装

echo.
echo   ==========================================================
echo      Llama Studio  首次运行环境安装
echo   ==========================================================
echo   程序目录: %CD%
echo.

rem ---- 挑选可用的 Python 解释器（全部相对，不写死任何路径） ----
set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto NO_PYTHON

echo [1/4] Python 解释器: %PY%

if exist ".venv\Scripts\python.exe" (
    echo [2/4] 虚拟环境 .venv 已存在，跳过创建。
) else (
    echo [2/4] 创建虚拟环境 .venv ...
    %PY% -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto VENV_FAILED

echo [3/4] 安装运行依赖（首次可能需要几分钟）...
if defined LLAMA_PIP_INDEX set "PIP_INDEX_URL=%LLAMA_PIP_INDEX%"
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto PIP_FAILED

echo [4/4] 生成本地启动器（按当前解释器位数重建，写入自定义图标）...
".venv\Scripts\python.exe" tools\build_launchers.py
if errorlevel 1 goto BUILD_FAILED

".venv\Scripts\python.exe" -c "import PySide6,sys; print('  环境就绪: PySide6 ' + PySide6.__version__ + ' / Python ' + sys.version.split()[0])"
if errorlevel 1 goto PIP_FAILED
echo.
echo   安装完成！双击 LlamaGUI.exe 启动软件（无控制台窗口）。
echo   换到别的电脑时，复制整个文件夹后重新运行本脚本即可。
echo   如需卸载，运行 uninstall.exe。
echo.
if not "%LLAMA_SILENT%"=="1" pause
exit /b 0

:NO_PYTHON
echo [错误] 未检测到可用的 Python 3.9+。
echo        请先安装 Python 并勾选 Add Python to PATH，然后重新运行本脚本。
goto FAIL
:VENV_FAILED
echo [错误] 虚拟环境创建失败，请确认 Python 安装完整（含 venv 模块）。
goto FAIL
:PIP_FAILED
echo [错误] 依赖安装失败。国内网络可先设置镜像再重试，例如：
echo        set LLAMA_PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
goto FAIL
:BUILD_FAILED
echo [错误] 启动器生成失败，请确认 tools\launcher 与 assets 目录完整。
goto FAIL
:FAIL
echo.
if not "%LLAMA_SILENT%"=="1" pause
exit /b 1
