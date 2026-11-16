@echo off
setlocal
cd /d "%~dp0"
uv run --project "%~dp0.." python -m uvicorn predict:app --port 9696
