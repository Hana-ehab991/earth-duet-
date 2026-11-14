# Earth Duet — Windows PowerShell quick start (Cairo + Aswan)

Run all commands in PowerShell from the extracted `earth-duet` folder. Needs Node.js LTS and Python 3.10+.

## 1. Install (first time only)
```powershell
cd path\to\earth-duet
.\setup-earth-duet.bat
```

## 2. Fetch real NASA POWER temperature for Cairo AND Aswan (fast, internet needed, no key)
```powershell
.\fetch-nasa-data.bat
# or directly:
.\backend\.venv\Scripts\python.exe scripts\fetch_historical.py --location cairo,aswan
```
Already have `data\raw\power_cairo_T2M_monthly.json` and want to skip the download?
`.\backend\.venv\Scripts\python.exe scripts\fetch_historical.py --location cairo --from-raw`

## 3. Start (close any old Earth Duet / uvicorn windows first; answer Y if asked to free port 8000)
```powershell
.\start-earth-duet.bat
```

## 4. Verify Cairo vs Aswan
```powershell
.\backend\.venv\Scripts\python.exe scripts\verify_cairo_aswan.py
Invoke-RestMethod "http://127.0.0.1:8000/api/health"
Invoke-RestMethod "http://127.0.0.1:8000/api/timeseries?location=aswan&variable=air_temperature" | Select-Object latest_complete_year, first_year
Invoke-RestMethod "http://127.0.0.1:8000/api/timeseries?location=cairo&variable=air_temperature"  | Select-Object latest_complete_year, first_year
```
Expected: both files `exists: true` in `/api/health`; Aswan's annual mean is a few degrees warmer than Cairo's every year.
Then in the browser (http://localhost:5173):
- **Time Travel** → choose Cairo or Aswan (the globe flies there; each shows its own series).
- **Color Symphony** → choose Cairo or Aswan; press Play; "Enable sound" to hear it.
- **Earth Duet** → "Example: Cairo vs Aswan" → Compare (MODIS NDVI via Google Earth Engine; needs `EE_PROJECT` in `backend\.env` and `earthengine authenticate`; otherwise an honest error is shown).

## Future projections (optional, very slow)
Not fetched by default; Time Travel labels them **unavailable**. Later, if you want to try: `.\fetch-projections.bat`
(resumable; add `--models ACCESS-CM2` inside the file for a one-model trial). Projections are only configured for Cairo.
