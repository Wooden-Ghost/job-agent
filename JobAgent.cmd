@echo off
chcp 65001 >nul
rem Job Agent launcher (source mode).
rem 找不到解释器时，可以设环境变量 JOBAGENT_PYTHON 指到 pythonw.exe / python.exe。
cd /d "%~dp0"

set "PY="
if defined JOBAGENT_PYTHON set "PY=%JOBAGENT_PYTHON%"
if not defined PY (
    where pythonw.exe >nul 2>nul
    if not errorlevel 1 set "PY=pythonw.exe"
)
if not defined PY (
    where pyw.exe >nul 2>nul
    if not errorlevel 1 set "PY=pyw.exe -3"
)
if not defined PY (
    where python.exe >nul 2>nul
    if not errorlevel 1 set "PY=python.exe"
)
if not defined PY (
    where py.exe >nul 2>nul
    if not errorlevel 1 set "PY=py.exe -3"
)

if not defined PY (
    echo.
    echo   [Job Agent] 没有找到 Python 运行环境。
    echo   请先安装 Python 3.12+，安装时勾选 "Add python.exe to PATH"。
    echo   下载：https://www.python.org/downloads/
    echo   装好了但它不在 PATH 里，也可以先设环境变量：
    echo       set JOBAGENT_PYTHON=D:\path\to\pythonw.exe
    echo.
    pause
    exit /b 1
)

start "" %PY% "%~dp0launch.py"
