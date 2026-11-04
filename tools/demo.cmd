@echo off
chcp 65001 >nul
rem 界面原型启动器：优先用 JOBAGENT_PYTHON，其次 PATH 里的 pythonw/py。
cd /d "%~dp0.."
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
    echo 找不到 Python，请装依赖后重试，或设 JOBAGENT_PYTHON 指向 pythonw.exe
    pause
    exit /b 1
)
start "" %PY% "%~dp0demo_table.py"
