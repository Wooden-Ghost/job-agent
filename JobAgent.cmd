@echo off
rem Job Agent launcher (ASCII only - cmd mangles non-ASCII batch files).
rem It looks for a Python that can import PySide6, then runs launch.py with pythonw.
setlocal
cd /d "%~dp0"
set "PYEXE="
set "CAND="
if exist "%~dp0python.txt" set /p CAND=<"%~dp0python.txt"
if defined CAND call :try "%CAND%"
if not defined PYEXE if defined JOBAGENT_PYTHON call :try "%JOBAGENT_PYTHON%"
if not defined PYEXE if exist "%~dp0.venv\Scripts\python.exe" call :try "%~dp0.venv\Scripts\python.exe"
if not defined PYEXE if exist "D:\Projects\Code\q_env\Scripts\python.exe" call :try "D:\Projects\Code\q_env\Scripts\python.exe"
if not defined PYEXE call :try "python.exe"
if not defined PYEXE goto :nodeps
set "PYW=%PYEXE:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PYEXE%"
start "" "%PYW%" "%~dp0launch.py"
exit /b 0
:try
if not exist "%~1" exit /b 0
"%~1" -c "import PySide6" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYEXE=%~1"
exit /b 0
:nodeps
echo.
echo   [Job Agent] No Python with PySide6 found.
echo   Fix: put the interpreter path into python.txt next to this file, e.g.
echo        D:\Projects\Code\q_env\Scripts\python.exe
echo   Or set JOBAGENT_PYTHON, or: pip install -r requirements.txt
echo.
pause
exit /b 1