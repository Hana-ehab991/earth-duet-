# Earth Duet — quick start (submission MVP)

1. First time only: double-click `setup-earth-duet.bat` (installs everything).
2. Put your Google Earth Engine project in `backend\.env` as a line `EE_PROJECT=your-project-id` (and run `earthengine authenticate` once).
3. Double-click `start-earth-duet.bat`. Two black windows open (keep them open) and the browser opens the **Earth Duet** tab.
4. Press **Example: Cairo vs Aswan**, then **Compare A and B**, then **Play duet**.

What it does: compares real NASA MODIS vegetation greenness (NDVI, 2010–2024, via Google Earth Engine) between two places you click on the globe, as charts, colours and a two-voice melody. Nothing is simulated; missing years are left blank/silent. Time Travel is unchanged. Full report: `docs/PHASE4_REPORT.md`.

---

# Earth Duet

Earth science data as synchronized **3D map + color + sound + chart + text**. Built for the NASA Space Apps *Earth Information Jukebox* challenge (independent project; not affiliated with or endorsed by NASA).

**Feature 1 — Time Travel** (implemented): pick Cairo, move through the **past** (NASA POWER T2M), the **present** (latest complete year) and the **future** (NASA NEX-GDDP-CMIP6, SSP2-4.5 / SSP5-8.5). Map, numbers, chart, Color Symphony and Tone.js sound all follow one shared timeline.
Features 2 (Earth Duet comparison) and 3 (Color Symphony explorer) are registered as *planned* and reuse the shared infrastructure — see `docs/ARCHITECTURE.md`.

> **Read this first — data status.** The build sandbox could not reach NASA hosts, so **no real NASA data is bundled**. The fetch scripts are implemented but were *not run against live services*. Until you run them, the app shows an honest "Data not fetched yet" state, or (opt-in) clearly-labelled **synthetic demo data**. See `IMPLEMENTATION_STATUS.md`.

## Quick start on Windows 11 (recommended)

1. Install **Node.js LTS** (https://nodejs.org/) and **Python 3.10+** (https://www.python.org/downloads/ - tick *Add python.exe to PATH*).
2. Unzip the project, then double-click **`setup-earth-duet.bat`** (first time only).
3. Double-click **`fetch-nasa-data.bat`** to download real NASA data (needs internet; no API key).
4. Double-click **`start-earth-duet.bat`** -> opens http://localhost:5173.
   Use `start-earth-duet.bat demo` for clearly-labelled synthetic DEMO data.

> The `.bat` files were written for Windows but could only be checked for line endings on Linux; they have **not** been executed on Windows. If one fails, the window stays open with the error text.

## Manual quick start (any OS)

Requirements: Python ≥ 3.10, Node ≥ 20.

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000          # API docs: http://127.0.0.1:8000/docs

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev                                        # http://localhost:5173  (proxies /api to :8000)
```

### Getting data
**Real data (needs internet access to NASA hosts):**
```bash
pip install -r backend/requirements-data.txt
python scripts/fetch_historical.py  --location cairo          # NASA POWER → data/processed/
python scripts/fetch_projections.py --location cairo --backend s3   # NEX-GDDP-CMIP6 (public S3, no key; slow, cached)
#   or: --backend ee   (Earth Engine; needs `earthengine authenticate` + EE_PROJECT)
python scripts/validate_data.py
```
**Demo data (synthetic, for UI testing only):**
```bash
python scripts/generate_demo_data.py
EARTH_DUET_DEMO_MODE=true uvicorn app.main:app --port 8000   # run from backend/
```
A red banner and `SYNTHETIC DEMO` badges are shown whenever demo data is served. Demo files live in `data/demo/`, real files in `data/processed/`; the API refuses synthetic data in `processed/`.

### Tests & checks
```bash
cd backend && python -m pytest ../tests/backend -q      # 18 tests
cd frontend && npm run typecheck && npm test && npm run build   # 28 tests
```

## Repository layout
```
backend/app/{api,services,schemas,models,utils}   FastAPI, validation, processing builders
data/{raw,processed,metadata,demo}                 raw payloads, validated real data, static metadata, synthetic demo
scripts/                                           fetch_historical / fetch_projections / validate_data / export_timeseries / generate_demo_data
frontend/src/core/                                 shared infrastructure (globe, api, timeline, color, audio, settings, provenance, ui)
frontend/src/features/{timeTravel,earthDuet,colorSymphony}   isolated features
frontend/src/app/                                  shell + feature registry (navigation)
tests/{backend,frontend}  docs/
```

## Scientific limitations (short)
* POWER T2M is **reanalysis/model-assisted** (not a station record); one grid cell (~0.5°×0.625°) at Cairo.
* NEX-GDDP-CMIP6 is **bias-corrected, downscaled model output** on a 0.25° grid; windows are 20-year means. Not a prediction, not city-block scale.
* The two products are **never spliced into one series**. Comparison across them uses anomalies against each product's own 1995–2014 baseline.
* Satellite imagery (GIBS) is single-day visual context, unrelated in resolution to the temperature products; availability not verified in the build environment.
Details: `docs/DATA_METHODOLOGY.md`.

## Credentials
None are required to run. Optional: Earth Engine project (`EE_PROJECT`) for one projection path; Cesium ion token (not needed). Never commit `.env`.

## Docs
`docs/ARCHITECTURE.md` · `DATA_SOURCES.md` · `DATA_METHODOLOGY.md` · `SONIFICATION.md` · `DEPLOYMENT.md` · `docs/spec/` (original requirements)
