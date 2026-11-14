@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Earth Duet - First-time setup
echo ==============================================
echo   Earth Duet - first-time setup
echo ==============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js was not found.
  echo   Install the LTS version from https://nodejs.org/ then run this file again.
  goto :fail
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found. Reinstall Node.js LTS from https://nodejs.org/
  goto :fail
)
set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (
  where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
  echo [ERROR] Python was not found.
  echo   Install Python 3.10+ from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" in the installer.
  goto :fail
)
for /f "delims=" %%v in ('node -v') do echo Node.js: %%v
for /f "delims=" %%v in ('npm -v') do echo npm:     %%v
for /f "delims=" %%v in ('%PYCMD% --version') do echo Python:  %%v
echo.

echo [1/4] Installing frontend dependencies (may take a few minutes)...
pushd frontend
call npm install
if errorlevel 1 ( popd & echo [ERROR] npm install failed. & goto :fail )
popd

echo.
echo [2/4] Creating Python virtual environment...
if not exist "backend\.venv\Scripts\python.exe" (
  %PYCMD% -m venv backend\.venv
  if errorlevel 1 ( echo [ERROR] Could not create the virtual environment. & goto :fail )
)

echo.
echo [3/4] Installing backend dependencies...
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
"backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 ( echo [ERROR] pip install failed. & goto :fail )

echo.
echo [4/4] Writing safe default settings...
if not exist "backend\.env" (
  > "backend\.env" echo EARTH_DUET_DEMO_MODE=false
  >> "backend\.env" echo EARTH_DUET_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
  echo Created backend\.env  ^(demo mode OFF - real data only^)
) else (
  echo backend\.env already exists - left unchanged.
)

echo.
echo ==============================================
echo   Setup finished.
echo ==============================================
if not exist "data\processed\cairo__air_temperature__observed.json" (
  echo NOTE: No real NASA data has been downloaded yet.
  echo   To download it ^(internet required, no API key needed^), run:
  echo     fetch-nasa-data.bat
  echo   Or start the app in clearly-labelled DEMO mode:
  echo     start-earth-duet.bat demo
)
echo.
echo Credentials: none required. ^(Optional: Google Earth Engine project, see README.^)
echo Next: double-click start-earth-duet.bat
echo.
pause
exit /b 0

:fail
echo.
echo Setup did not finish. Fix the problem above and run this file again.
pause
exit /b 1
