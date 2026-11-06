@echo off
rem ===========================================================================
rem  Llama Studio - first run setup (Windows 10 / 11)
rem  All paths are relative to this file, so the whole folder can be copied.
rem  Optional environment variables for unattended runs:
rem    LLAMA_SILENT       skip the final "Press any key" prompt
rem    LLAMA_PY_INDEX     pre-select a Python when several are installed
rem    LLAMA_PIP_INDEX    force one package index and skip the speed test
rem ===========================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Llama Studio - First Run Setup

set "ROOT=%~dp0"
set "LIST=%TEMP%\llama_python_%RANDOM%%RANDOM%.txt"
set "MIRRORS=%TEMP%\llama_mirrors_%RANDOM%%RANDOM%.txt"
set "BEST=%TEMP%\llama_best_%RANDOM%%RANDOM%.txt"
set "COUNT=0"
set "INDEX="
set "INSTALL_OK=0"
set "EXITCODE=0"

echo.
echo  ==========================================================
echo   Llama Studio - first run setup
echo  ==========================================================
echo.

rem ---------------------------------------------------------------- [1] Python
echo  [1] Detecting Python installations ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%tools\detect_python.ps1" -Out "%LIST%" -Root "%ROOT%" >nul 2>&1
if not exist "%LIST%" type nul > "%LIST%"

for /f "usebackq tokens=1,2 delims=|" %%A in ("%LIST%") do (
    set /a COUNT+=1
    set "PY_!COUNT!=%%A"
    set "PYV_!COUNT!=%%B"
)

if "!COUNT!"=="0" goto :NO_PYTHON
if "!COUNT!"=="1" goto :ONE_PYTHON

echo      Found !COUNT! usable 64-bit Python installations:
for /l %%i in (1,1,!COUNT!) do echo        [%%i] !PY_%%i!   Python !PYV_%%i!
echo.
set "IDX=1"
if defined LLAMA_PY_INDEX set "IDX=%LLAMA_PY_INDEX%"
if not defined LLAMA_PY_INDEX if not defined LLAMA_SILENT set /p "IDX=     Select one [1-!COUNT!], default 1: "
echo.
goto :VALIDATE

:ONE_PYTHON
echo      Found 1 usable Python: !PY_1!   Python !PYV_1!
set "IDX=1"
goto :VALIDATE

:NO_PYTHON
echo      No usable 64-bit Python 3.9 or newer was found on this computer.
echo      Opening the official download page: https://www.python.org/downloads/
start "" "https://www.python.org/downloads/"
echo      Install Python 3.9 or newer, then run first_run.bat again.
goto :FAIL

:VALIDATE
echo(!IDX!| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 set "IDX=1"
if !IDX! LSS 1 set "IDX=1"
if !IDX! GTR !COUNT! set "IDX=1"
call set "PY=%%PY_!IDX!%%"
call set "PYVER=%%PYV_!IDX!%%"
if not defined PY goto :FAIL
echo      Using: !PY!   Python !PYVER!

rem ------------------------------------------------------------- [2] Virtual env
echo.
echo  [2] Preparing the virtual environment .venv ...
set "REBUILD=0"
if not exist ".venv\Scripts\python.exe" set "REBUILD=1"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if errorlevel 1 set "REBUILD=1"
    if "!REBUILD!"=="0" (
        ".venv\Scripts\python.exe" "%ROOT%tools\check_venv.py" --selected "!PY!" >nul 2>&1
        if errorlevel 1 set "REBUILD=1"
    )
)
if "!REBUILD!"=="1" (
    echo      Creating .venv with the selected Python !PYVER! ...
    "!PY!" -m venv --clear .venv
    if errorlevel 1 goto :VENV_FAIL
) else (
    echo      Existing .venv is usable - skipped.
)
if not exist ".venv\Scripts\python.exe" goto :VENV_FAIL

rem --------------------------------------------------------------- [3] Mirrors
echo.
echo  [3] Selecting the fastest package index ...
if defined LLAMA_PIP_INDEX goto :INDEX_OVERRIDE
".venv\Scripts\python.exe" "%ROOT%tools\select_mirror.py" --out "%MIRRORS%" --best "%BEST%" >nul
if not exist "%MIRRORS%" call :WRITE_DEFAULT_MIRRORS
if exist "%BEST%" for /f "usebackq delims=" %%I in ("%BEST%") do set "INDEX=%%I"
if not defined INDEX set "INDEX=https://pypi.org/simple"
echo      Using: !INDEX!
goto :INSTALL

:INDEX_OVERRIDE
set "INDEX=%LLAMA_PIP_INDEX%"
> "%MIRRORS%" echo %LLAMA_PIP_INDEX%
echo      Using LLAMA_PIP_INDEX override: !INDEX!
goto :INSTALL

rem -------------------------------------------------------------- [4] Packages
:INSTALL
echo.
echo  [4] Installing Python packages ...
for /f "usebackq delims=" %%I in ("%MIRRORS%") do (
    if "!INSTALL_OK!"=="0" (
        echo      Trying: %%I
        ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --timeout 25 --retries 2 -i "%%I" -r "%ROOT%requirements.txt"
        if not errorlevel 1 set "INSTALL_OK=1"
    )
)
if "!INSTALL_OK!"=="0" goto :PIP_FAIL

rem ------------------------------------------------------------- [5] Launchers
echo.
echo  [5] Rebuilding launchers, runtime interpreter and custom icons ...
".venv\Scripts\python.exe" "%ROOT%tools\build_launchers.py"
if errorlevel 1 goto :BUILD_FAIL

rem ------------------------------------------------------------------- [6] Done
echo.
echo  [6] Setup complete.
echo      Run LlamaGUI.exe to start Llama Studio.
echo      To serve the API without a window, start the service and click
echo      "Run in background", or use a shortcut with --tray --start-server.
echo.
goto :CLEANUP

:VENV_FAIL
echo      ERROR: could not create .venv with the selected Python.
goto :FAIL
:PIP_FAIL
echo      ERROR: every package index failed. Check the network and retry.
goto :FAIL
:BUILD_FAIL
echo      ERROR: failed to rebuild the launchers.
goto :FAIL
:FAIL
set "EXITCODE=1"
echo      Setup did not finish. Fix the issue above, then run first_run.bat again.

:CLEANUP
if exist "%LIST%" del /q "%LIST%" >nul 2>&1
if exist "%MIRRORS%" del /q "%MIRRORS%" >nul 2>&1
if exist "%BEST%" del /q "%BEST%" >nul 2>&1
if not defined LLAMA_SILENT pause
endlocal & exit /b %EXITCODE%

:WRITE_DEFAULT_MIRRORS
> "%MIRRORS%" echo https://pypi.org/simple
>>"%MIRRORS%" echo https://pypi.tuna.tsinghua.edu.cn/simple
>>"%MIRRORS%" echo https://mirrors.aliyun.com/pypi/simple
>>"%MIRRORS%" echo https://mirrors.ustc.edu.cn/pypi/simple
>>"%MIRRORS%" echo https://mirrors.cloud.tencent.com/pypi/simple
>>"%MIRRORS%" echo https://repo.huaweicloud.com/repository/pypi/simple
exit /b 0
