@echo off
REM build_exe.bat - Builds a single-file Windows exe using PyInstaller
REM Usage: run in an activated virtualenv, or remove venv steps if you prefer global env

@echo off
REM build_exe.bat - Builds the project using PyInstaller via the python -m invocation
REM Usage: Run this in an activated virtualenv (recommended) or a system Python where dependencies are installed.

REM Optional: create & activate a venv (first time only)
REM python -m venv .venv
REM .\.venv\Scripts\Activate.ps1   <-- in PowerShell

REM Install requirements into the active Python environment
python -m pip install -r requirements.txt

REM Clean previous build artifacts
rmdir /s /q build >nul 2>&1
rmdir /s /q dist >nul 2>&1
if exist BPSR-Module-Optimizer.exe del /q BPSR-Module-Optimizer.exe >nul 2>&1

REM Build using PyInstaller via the module interface to avoid PATH issues
python -m PyInstaller --clean --noconfirm gui_app.spec

IF %ERRORLEVEL% NEQ 0 (
	echo PyInstaller failed. Check the output above for errors.
	pause
	exit /b %ERRORLEVEL%
)

echo Build finished. Output is in the dist\ folder (or in the folder named by the spec).
echo If you used --onedir you will find a folder; for --onefile change the spec or command accordingly.
pause