@echo off
setlocal
cd /d %~dp0backend

for %%F in (main.py settings.py auth.py risk_baseline.py notifications.py requirements.txt) do (
  if not exist "%%F" (
    echo [PRAHARI] Missing backend file: %%F
    echo This folder is incomplete or mixed with an older version.
    echo Please use the complete PRAHARI v9 package.
    pause
    exit /b 1
  )
)

if not exist .venv\Scripts\python.exe (
  echo [PRAHARI] Creating Python virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate
python -c "import fastapi,uvicorn,sklearn,joblib,pandas,numpy,multipart,dotenv,twilio" >nul 2>&1
if errorlevel 1 (
  echo [PRAHARI] Installing backend dependencies...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [PRAHARI] Dependency installation failed.
    pause
    exit /b 1
  )
)

echo [PRAHARI] Starting backend at http://127.0.0.1:8000
uvicorn main:app --reload
