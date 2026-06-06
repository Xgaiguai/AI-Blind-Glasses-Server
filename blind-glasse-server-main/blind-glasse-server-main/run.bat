@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 5000 --log-level warning --no-access-log
) else (
  python -m uvicorn main:app --host 0.0.0.0 --port 5000 --log-level warning --no-access-log
)
pause
