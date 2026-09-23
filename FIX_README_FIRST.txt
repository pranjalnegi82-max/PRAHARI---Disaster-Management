PRAHARI v9 FIXED PACKAGE

If you previously saw:
    ModuleNotFoundError: No module named 'settings'
that happened because backend/main.py from v9 was placed inside an older/incomplete v8 folder without settings.py, auth.py and risk_baseline.py.

Do not mix v8 and v9 files.

Recommended startup:
1. Extract this package to a NEW folder, e.g. F:\PRAHARI_v9_FIXED
2. Double-click start_all.bat
3. Backend should open at http://127.0.0.1:8000
4. Frontend should open at the Vite address, normally http://127.0.0.1:5173
5. Verify backend: http://127.0.0.1:8000/docs

If the frontend dependencies are already cached globally or internet is available, npm install will run automatically when needed.
