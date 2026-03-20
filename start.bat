@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo TSPP Clinical Data Extraction - Fast Setup (Windows)
echo ===================================================

:: 1. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [x] Python could not be found. Please install Python and ensure it is added to your PATH.
    pause
    exit /b 1
)

:: 2. Load .env safely if it exists (ignoring comments and empty lines)
if exist .env (
    for /f "tokens=1,* delims==" %%A in ('type .env ^| findstr /v "^#" ^| findstr /r "."') do (
        set "%%A=%%B"
    )
)

:: 3. Check for GOOGLE_API_KEY
if "!GOOGLE_API_KEY!"=="" (
    echo.
    echo [!] GOOGLE_API_KEY is missing.
    set /p NEW_KEY="Please enter your GOOGLE_API_KEY: "
    
    :: Save to .env and set in current session
    echo GOOGLE_API_KEY=!NEW_KEY!>> .env
    set "GOOGLE_API_KEY=!NEW_KEY!"
    echo [✓] API Key saved to .env file!
)

:: 4. Install dependencies automatically
echo.
echo [*] Checking and installing missing dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [x] Failed to install dependencies. Please check your internet connection or pip installation.
    pause
    exit /b %errorlevel%
)

:: 5. Run the Frontend App smoothly via python module target
echo.
echo [*] Starting the TSPP Frontend...
set "STREAMLIT_GATHER_USAGE_STATS=false"
python -m streamlit run app.py --logger.level=error

pause
