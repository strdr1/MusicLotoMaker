@echo off
chcp 65001
echo ===============================
echo   Music Loto Maker Launcher
echo ===============================
echo.

echo Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.7+
    pause
    exit
)

echo Installing dependencies...
pip install pywebview

echo Starting application...
python app.py

echo.
echo Application closed.
pause