@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0.."

uv sync --project "%ROOT%"
if errorlevel 1 exit /b 1

if /i "%~1"=="exec" (
    uv run --project "%ROOT%" python -m nbconvert --to notebook --execute --inplace ^
        --ExecutePreprocessor.timeout=900 notebook.ipynb
    exit /b %errorlevel%
)

uv run --project "%ROOT%" python -m jupyterlab notebook.ipynb
