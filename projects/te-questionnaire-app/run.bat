@echo off
REM Launch ThousandEyes QA Automator (source / developer mode on Windows)
cd /d "%~dp0"

if not exist ".venv" (
    echo Setting up for the first time...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

python launcher.py %*
