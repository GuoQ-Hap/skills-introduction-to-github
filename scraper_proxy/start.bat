@echo off
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1

echo ========================================
echo  Amazon Scraper Proxy - Windows VM
echo  Dir: %cd%
echo  Log: %cd%\scraper_proxy.log
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

if exist venv (
    if not exist venv\Scripts\python.exe (
        echo [WARN] Existing venv is broken, recreating...
        rmdir /s /q venv
    ) else (
        venv\Scripts\python.exe --version >nul 2>&1
        if errorlevel 1 (
            echo [WARN] Existing venv points to a missing Python, recreating...
            rmdir /s /q venv
        )
    )
)

if not exist venv (
    echo [1/3] Creating venv...
    python -m venv venv
)

echo [2/3] Installing dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
python -c "from playwright.sync_api import sync_playwright; print('Playwright package OK')" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Playwright Python package import failed.
    echo Try manually:
    echo   venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo [2/3] Installing Playwright Chromium...
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
python -m playwright install chromium
if errorlevel 1 (
    echo [WARN] Mirror download failed, retrying official Playwright CDN...
    set PLAYWRIGHT_DOWNLOAD_HOST=
    python -m playwright install chromium
)
if errorlevel 1 (
    echo [ERROR] Playwright Chromium install failed. Please check network/proxy.
    echo Try manually:
    echo   set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
    echo   venv\Scripts\python.exe -m playwright install chromium
    pause
    exit /b 1
)

echo [3/3] Starting scraper proxy...
echo.
python -u scraper_server.py --host 0.0.0.0 --port 9100
pause
