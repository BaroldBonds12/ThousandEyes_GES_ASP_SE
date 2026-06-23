@echo off
REM ============================================================
REM  Build Windows distributable for ThousandEyes QA Automator
REM  Produces: dist\TE_Questionnaire_Automator\  (folder)
REM            dist\TE_QA_Automator_win.zip
REM
REM  Run this on a Windows PC. Output can be sent to any Windows user.
REM ============================================================

echo ============================================================
echo  Building ThousandEyes QA Automator -- Windows
echo ============================================================
echo.

cd /d "%~dp0"

REM ---- Prerequisites ----
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [OK] Python %%v

REM ---- Virtual environment ----
if not exist ".venv" (
    echo [..] Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet

echo [..] Installing runtime dependencies...
pip install -r requirements.txt --quiet

echo [..] Installing PyInstaller...
pip install -r build_requirements.txt --quiet

REM ---- Clean ----
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

REM ---- Build ----
echo.
echo [..] Building Windows executable (this takes 1-3 minutes)...
pyinstaller te_qa.spec --clean --noconfirm

echo.
echo [OK] Build complete!
echo      App folder: dist\TE_Questionnaire_Automator\
echo.

REM ---- Zip for distribution ----
echo [..] Creating ZIP archive...
powershell -Command "Compress-Archive -Path 'dist\TE_Questionnaire_Automator' -DestinationPath 'dist\TE_QA_Automator_win.zip' -Force"

echo [OK] ZIP created: dist\TE_QA_Automator_win.zip
echo.
echo ============================================================
echo  How to distribute:
echo    Send dist\TE_QA_Automator_win.zip to the recipient.
echo    They unzip it and run TE_Questionnaire_Automator.exe
echo    The wizard installs Ollama on first launch.
echo ============================================================
echo.
pause
