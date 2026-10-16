@echo off
setlocal EnableDelayedExpansion
title QR Code Builder – Setup

echo.
echo  ╔══════════════════════════════════════╗
echo  ║       QR Code Builder  Setup         ║
echo  ╚══════════════════════════════════════╝
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Please install Python 3.10+ from https://python.org and re-run this script.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Python: %%v

echo.
echo  [1/3] Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] pip install failed. Check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo  [2/3] Generating app icon...
python make_icon.py
if errorlevel 1 (
    echo  [WARNING] Icon generation failed. App will run without a custom icon.
)

echo.
echo  [3/3] Setup complete!
echo.
echo  ─────────────────────────────────────────
echo   To run:             python main.py
echo   Desktop shortcut:   launch the app and
echo                        click the button
echo                        in the Actions area
echo  ─────────────────────────────────────────
echo.

set /p LAUNCH="  Launch the app now? [Y/n]: "
if /i "!LAUNCH!" neq "n" (
    echo.
    echo  Starting QR Code Builder...
    start "" pythonw main.py
)

endlocal
