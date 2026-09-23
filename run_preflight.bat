@echo off
cd /d "%~dp0"
echo PRAHARI v8 Research-Synthesis Preflight
python qa\smoke_test.py
pause
