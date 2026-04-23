@echo off
cd /d "%~dp0"

echo ========================================
echo  Amazon Scraper Proxy - Windows VM
echo  Dir: %cd%
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

if not exist venv (
    echo [1/3] Creating venv...
    python -m venv venv
)

echo [2/3] Installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt -q

echo [3/3] Starting scraper proxy...
echo.
python scraper_server.py --host 0.0.0.0 --port 9100
pause
