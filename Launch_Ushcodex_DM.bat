@echo off
title Ushcodex Download Manager
cd /d "%~dp0"
python ushcodex_dm.py
if errorlevel 1 (
    echo.
    echo Failed to launch GUI. Please make sure Python 3 is installed.
    pause
)
