@echo off
setlocal
cd /d "%~dp0"
uv run --isolated --no-project --with-requirements requirements-serve.txt python tools\run_verification.py
pause
