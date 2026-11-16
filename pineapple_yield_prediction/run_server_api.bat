@echo off
setlocal
cd /d "%~dp0"
uv run --isolated --no-project --with-requirements requirements-serve.txt python predict.py
