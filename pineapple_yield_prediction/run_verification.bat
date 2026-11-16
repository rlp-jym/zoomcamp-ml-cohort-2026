@echo off
setlocal
cd /d "%~dp0"
uv run --project "%~dp0.." python tools\run_verification.py
pause
