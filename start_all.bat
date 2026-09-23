@echo off
cd /d %~dp0
start "PRAHARI Backend" cmd /k call start_backend.bat
timeout /t 3 /nobreak >nul
start "PRAHARI Frontend" cmd /k call start_frontend.bat
echo PRAHARI launch started. Open the Vite URL shown in the frontend window.
pause
