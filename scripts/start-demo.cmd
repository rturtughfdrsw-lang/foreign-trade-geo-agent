@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Setup required: create .venv, then run `python -m pip install -e ".[demo]"`.
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\start_demo.py"
