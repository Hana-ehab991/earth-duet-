@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Earth Duet launcher
REM Usage: start-earth-duet.bat          (real data only)
REM        start-earth-duet.bat demo     (synthetic DEMO data, clearly labelled)

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] Backend is not set up yet. Run setup-earth-duet.bat first.
  goto :fail
)
if not exist "frontend\node_modules" (
  echo [ERROR] Frontend is not set up yet. Run setup-earth-duet.bat first.
  goto :fail
)

set "HAS_EE=0"
if defined EE_PROJECT set "HAS_EE=1"
if exist "backend\.env" findstr /b /i /c:"EE_PROJECT=" "backend\.env" >nul 2>nul && set "HAS_EE=1"
if "%HAS_EE%"=="0" (
  echo [NOTE] EE_PROJECT is not set in backend\.env. Time Travel works, but the Earth Duet comparison needs your
  echo        Google Earth Engine project. Add a line like  EE_PROJECT=your-project-id  to backend\.env ^(see README^).
)

REM --- Port 8000 must be free, otherwise the frontend (which proxies /api to :8000) talks to an OLD server
REM     that may be running from another copy of the project and cannot see the data you just fetched.
set "PORT_PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do set "PORT_PID=%%p"
if defined PORT_PID (
  echo.
  echo [WARNING] Something is already listening on port 8000 ^(process id %PORT_PID%^).
  echo           It is probably an older Earth Duet backend, possibly from a different folder.
  choice /c YN /m "Stop that process and continue"
  if errorlevel 2 goto :fail
  taskkill /PID %PORT_PID% /F >nul 2>nul
  timeout /t 2 /nobreak >nul
)

set "DEMO=false"
if /i "%~1"=="demo" set "DEMO=true"
if "%DEMO%"=="true" (
  echo *** DEMO MODE: DEMO DATA - NOT SCIENTIFIC MEASUREMENTS ***
) else (
  echo REAL DATA MODE. If no NASA data was fetched, the app will say so.
)

echo Starting backend on http://127.0.0.1:8000 ...
start "Earth Duet backend" /D "%~dp0backend" cmd /k "set EARTH_DUET_DEMO_MODE=%DEMO%&& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Starting frontend on http://localhost:5173 ...
start "Earth Duet frontend" /D "%~dp0frontend" cmd /k "npm run dev -- --host 127.0.0.1 --port 5173"

echo Waiting for the servers to start...
timeout /t 10 /nobreak >nul
start "" "http://localhost:5173/#/earth-duet"

echo.
echo ==============================================
echo   Earth Duet:  http://localhost:5173
echo   API docs:    http://127.0.0.1:8000/docs
echo   Data check:  http://127.0.0.1:8000/api/health   ^(shows which data folder the backend reads^)
echo ==============================================
echo Two windows opened (backend, frontend). Close them to stop the app.
echo If the page does not load, read the error text in those windows.
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
