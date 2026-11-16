@echo off
setlocal
cd /d "%~dp0"
uv run --project "%~dp0.." python train.py
pause
