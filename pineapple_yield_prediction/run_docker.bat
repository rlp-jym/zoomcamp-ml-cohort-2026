@echo off
setlocal
cd /d "%~dp0"

set START=%TIME%
docker build -t pineapple-yield .
set BUILD_EXIT=%ERRORLEVEL%
set END=%TIME%
call :elapsed

if not "%BUILD_EXIT%"=="0" (
    echo.
    echo Build failed. Is Docker Desktop running?
    pause
    exit /b 1
)

docker run --rm -p 9696:9696 pineapple-yield
pause
exit /b 0

:elapsed
for /f "tokens=1-4 delims=:.," %%a in ("%START%") do set /a start_s=(((%%a*60)+1%%b %% 100)*60+1%%c %% 100)
for /f "tokens=1-4 delims=:.," %%a in ("%END%") do set /a end_s=(((%%a*60)+1%%b %% 100)*60+1%%c %% 100)
set /a elapsed_s=end_s-start_s
if %elapsed_s% lss 0 set /a elapsed_s+=86400
set /a elapsed_m=elapsed_s/60
set /a elapsed_r=elapsed_s%%60
echo.
echo Build time: %elapsed_m%m %elapsed_r%s
echo.
exit /b
