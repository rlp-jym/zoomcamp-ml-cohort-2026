@echo off
setlocal
cd /d "%~dp0"

docker build -t pineapple-yield .
if errorlevel 1 (
    echo.
    echo Build failed. Is Docker Desktop running?
    pause
    exit /b 1
)

docker run --rm -p 9696:9696 pineapple-yield
pause
