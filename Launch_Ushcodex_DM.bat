@echo off
title Ushcodex Download Manager
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw ushcodex_dm.py
    exit /b 0
)

python ushcodex_dm.py
if errorlevel 1 (
    echo.
    echo Failed to launch GUI. Please make sure Python 3 is installed.
    pause
)
