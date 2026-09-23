@echo off
cd /d "%~dp0"
echo ========================================================
echo PRAHARI - PREPARE OFFLINE SATELLITE FOR COLLEGE DEMO
echo ========================================================
echo.
echo 1. Make sure start_backend.bat is already running.
echo 2. Run this while you have GOOD internet (home/hotspot).
echo 3. Only low-zoom Northeast India NASA tiles are cached.
echo.
python tools\warm_satellite_cache.py
pause
