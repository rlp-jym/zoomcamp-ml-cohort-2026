@echo off
setlocal
cd /d "%~dp0"
uv run --project "%~dp0.." python run_prediction.py
pause
