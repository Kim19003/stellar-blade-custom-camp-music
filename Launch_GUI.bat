@echo off
setlocal
cd /d "%~dp0"
title Stellar Blade Camp Music Injector

:: Prefer pythonw to launch cleanly without keeping a background cmd window open
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw camp_music_gui.py %*
    exit /b 0
)

:: Fallback to python
where python >nul 2>&1
if %errorlevel% equ 0 (
    start "" python camp_music_gui.py %*
    exit /b 0
)

:: Fallback to Windows Python launcher 'py'
where py >nul 2>&1
if %errorlevel% equ 0 (
    start "" py -3 camp_music_gui.py %*
    exit /b 0
)

echo [ERROR] Python was not found on your system PATH.
echo Please install Python 3.10 or newer from https://www.python.org/
echo (Make sure to check "Add Python to PATH" during installation.)
echo.
pause
exit /b 1
