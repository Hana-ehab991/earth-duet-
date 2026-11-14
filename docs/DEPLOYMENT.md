# Deployment

**Backend (Render / Railway / any Python host)** — root `backend/`; build `pip install -r requirements.txt`; start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set `EARTH_DUET_CORS_ORIGINS=https://<your-frontend>`; leave `EARTH_DUET_DEMO_MODE` unset/false. The API reads `data/` — commit the **validated** `data/processed/*.json` produced by the fetch scripts (not `data/raw`, not secrets), or mount it as a disk. The fetch scripts run locally/CI, not on the web host.

**Frontend (Vercel / Netlify)** — root `frontend/`; build `npm run build` (the `prebuild` hook copies Cesium assets to `public/cesium`); output `dist`; set `VITE_API_BASE_URL=https://<your-backend>`. SPA hash routing needs no rewrites. Serve over HTTPS (Web Audio and CORS).

**Credentials needed:** none to run. Optional: `EE_PROJECT` (Earth Engine, data script only), `VITE_CESIUM_ION_TOKEN` (public, URL-restrict it).

**Before a public demo:** run both fetch scripts, `scripts/validate_data.py`, confirm `/api/health` shows `"cairo":"configured"` and `demo_mode:false`, and verify GIBS tiles load for a few years.
