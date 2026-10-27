@echo off
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Run tools\install-desktop.ps1 first.
    pause
    exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -m opensim.desktop
