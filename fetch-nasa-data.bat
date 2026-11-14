@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Earth Duet - fetch NASA POWER data (Cairo + Aswan)
if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] Run setup-earth-duet.bat first.
  pause & exit /b 1
)
if not exist "data\raw" mkdir "data\raw"
if not exist "data\raw\nex_gddp" mkdir "data\raw\nex_gddp"
if not exist "data\processed" mkdir "data\processed"

"backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements-data.txt
if errorlevel 1 ( echo [ERROR] Could not install data dependencies. & pause & exit /b 1 )
echo.
echo [1/2] NASA POWER historical temperature for Cairo AND Aswan (observed / reanalysis, fast)...
"backend\.venv\Scripts\python.exe" scripts\fetch_historical.py --location cairo,aswan
if errorlevel 1 ( echo [ERROR] At least one POWER fetch failed. See messages above. Nothing was invented. & pause & exit /b 1 )
echo.
echo [2/2] Validating...
"backend\.venv\Scripts\python.exe" scripts\validate_data.py
echo.
echo NOTE: Future climate projections are NOT fetched here (very slow). Time Travel labels them unavailable.
echo       Optional, later: fetch-projections.bat
echo Restart the backend (close its window, run start-earth-duet.bat) so it re-reads data\processed.
pause
