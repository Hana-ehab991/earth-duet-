@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Earth Duet - OPTIONAL slow NEX-GDDP-CMIP6 projections
if not exist "backend\.venv\Scripts\python.exe" ( echo [ERROR] Run setup-earth-duet.bat first. & pause & exit /b 1 )
echo This can take hours. Finished downloads are cached; Ctrl+C and re-run to resume.
echo Quick single-model trial: add  --models ACCESS-CM2
"backend\.venv\Scripts\python.exe" scripts\fetch_projections.py --location cairo --backend auto
if errorlevel 1 echo [WARNING] Projections unavailable; nothing was written or invented.
pause
