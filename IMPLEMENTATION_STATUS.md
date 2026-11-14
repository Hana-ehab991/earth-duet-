# Implementation status

Legend: ✅ Fully implemented and tested · 🟡 Implemented but not tested · 🟠 Partially implemented · 🔒 Blocked by external data/credentials · ❌ Not implemented

Tested = automated tests and/or driven in headless Chromium in this sandbox. Date of status: 2026-11-12.

## Key blocker
NASA POWER, NASA GIBS and the NEX-GDDP-CMIP6 S3 bucket were **unreachable from the build sandbox** (HTTP 403 from the egress proxy). **No real NASA data was downloaded**, so no real scientific value has ever been displayed by this build. Everything marked 🔒 needs a run on a machine with internet access (`scripts/fetch_*.py`).

## Platform / architecture
| Feature | Status | Notes |
|---|---|---|
| Feature-based frontend (`core/` vs `features/`), feature registry & navigation | ✅ | Time Travel + two "planned" stubs render; `core` never imports `features` |
| Reusable services: globe, API client, timeline factory, color engine, audio engine, provenance | ✅ | Timeline/color/audio math unit-tested; globe driven in browser |
| Earth Duet comparison feature | ❌ | Stub page only (by design) |
| Color Symphony standalone explorer | ❌ | Stub page; the engine itself is ✅ and used by Time Travel |

## Backend
| Feature | Status | Notes |
|---|---|---|
| FastAPI app, CORS, structured errors, parameter validation | ✅ | 18 pytest tests |
| `/api/health,locations,variables,scenarios,timeseries,climate,imagery/metadata,provenance` | ✅ | Tested against demo and no-data states |
| Schemas with mandatory provenance; synthetic data isolated from `processed/` | ✅ | Tested (API rejects synthetic data in `processed/`) |
| Other locations never get Cairo data (`dataset_not_configured`, HTTP 501) | ✅ | Tested |
| Processing (K→°C, 12-month rule, window centring/clipping, ensemble stats) | ✅ | Unit-tested with synthetic *fixtures* (arithmetic only) |

## Data integration
| Feature | Status | Notes |
|---|---|---|
| NASA POWER T2M fetch + annual build (`fetch_historical.py`) | 🔒 | Code implemented; builder tested on a synthetic payload; **never run against the live API**. Response layout follows public docs — unverified. Script fails honestly and writes nothing when blocked (observed) |
| NEX-GDDP-CMIP6 extraction (`fetch_projections.py`, `s3` and `ee` backends) | 🔒 | Builder/assembly tested with a test double; S3 key pattern, model/variant/grid labels, and Earth Engine call are **untested** against live services |
| GIBS imagery integration | 🔒 | Implemented (date-per-year URL, availability logic tested, runtime tile-failure → labelled base map observed working). Actual tile availability never verified; layer/start date from public docs |
| Validation / CSV export scripts | 🟡 | `validate_data.py` run on demo data; `export_timeseries.py` not run |
| Synthetic demo mode | ✅ | Clearly labelled (banner, badges, `DEMO-MODEL-*`); labelled illustrative values |

## Time Travel UI
| Feature | Status | Notes |
|---|---|---|
| 3D Cesium globe, fly-to, markers, coordinates, legend, attribution | ✅ | Rendered in headless Chromium (SwiftShader). Base map is low-res bundled Natural Earth II |
| Location selector (Cairo / Greenland / Amazon, "Dataset not configured") | ✅ | Driven in browser |
| Past / Present / Future modes, slider, play/pause, speed, prev/next, availability track | ✅ | Driven in browser; store/resolver unit-tested |
| Honest unavailable/gap/incomplete-year states | ✅ | Unit + browser tested |
| Readout panel (value, unit, source, type, scenario, models, anomaly, spread) | ✅ | Verified with demo data only |
| Scenario selector changes data; scenario comparison table | ✅ | Verified against demo data (values change 22.81→22.91 °C for 2030) |
| Chart (separate observed/projection series, spread bars, data table) | ✅ | Verified with demo data; observed line and projections are never joined |
| Color Symphony (fixed scale, legend with real values, CVD palette, disable effects) | ✅ | Deterministic color unit-tested; visual check in browser |
| Sonification (Tone.js, enable gesture, volume, mute, calibration, ping/sustain, text alternative) | 🟡 | Mapping math unit-tested; enable/calibration state machine verified in headless Chromium. **Audible output, loudness and clipping were not heard/measured** |
| Race-safe async (abort stale, debounce imagery) | 🟡 | Implemented by design (`useAsyncResource`, debounce); no dedicated race test |
| Keyboard, ARIA labels/valuetext, live regions, reduced motion, high contrast, text alternatives | 🟠 | Slider keyboard use verified; **no screen-reader or axe/contrast audit was run**; high-contrast mode is a basic override |
| Responsive layout | 🟠 | Desktop + 390 px viewport checked by screenshot; no horizontal scroll; panels sit below the globe on mobile; no real-device test |
| Future map = projected overlay, not imagery | ✅ | Grid-cell rectangle colored by value, labelled as projected climate overlay. **No raster field is rendered** — only the point's native grid cell |

## Not done / known gaps
* No real data loaded → no real-data end-to-end verification (acceptance items 4, 10, 11 depend on it).
* Overlay is a single grid cell, not a spatial temperature raster (needs gridded extraction; point extraction only in MVP).
* No frontend component tests or automated browser tests are committed (the Playwright run was ad-hoc).
* Cesium bundle is large (~4 MB, 1.1 MB gzip), lazy-loaded.
* Model list and POWER/NEX-GDDP grid sizes should be confirmed against current catalogs.

## Next steps to reach acceptance
1. On a networked machine: `fetch_historical.py`, `fetch_projections.py`, `validate_data.py`; check `/api/health` → `configured`.
2. Spot-check 2–3 values against POWER/Earth Engine by hand; confirm models and GIBS tiles for several years.
3. Listen-test the audio at several volumes; run a screen-reader and automated accessibility pass.

## Update 2026-11-13 (repair pass)
| Item | Status | Notes |
|---|---|---|
| `npm install`, typecheck, `vite build`, 28 vitest tests | ✅ | Run on Linux (Node 22). Not run on Windows |
| 18 backend pytest tests | ✅ | Run on Linux (Python 3.12) |
| Backend start, `/api/health`, Vite `/api` proxy | ✅ | Verified with curl in demo mode (Linux) |
| `setup-earth-duet.bat`, `start-earth-duet.bat`, `fetch-nasa-data.bat` | 🟡 | Added; CRLF checked; **never executed on Windows** |
| `backend/.env` loading | ✅ | Small loader added in `config.py` |
| NASA POWER / GIBS / NEX-GDDP-CMIP6 | 🔒 | Unreachable from this sandbox. No real data fetched; S3 key pattern and GIBS tile availability unverified |
| Browser/visual re-test, audible sound test | ❌ | Not repeated in this pass |

## Update 2026-11-13 (Phase 3: comparison API + cache)
| Item | Status | Notes |
|---|---|---|
| `POST /api/compare-locations`, `GET /api/comparison/status` | 🟡 | Implemented. Service/cache logic tested with a **mocked** Earth Engine; the FastAPI layer's tests are written but were not run in the build sandbox (no fastapi/pytest installable). Not reachable from the UI |
| SQLite cache (`data/cache/comparison.sqlite`) | ✅ | Tested with temporary databases (hit/miss, restart persistence, invalidation, corruption, expiry, concurrency) |
| Live Earth Engine retrieval | 🔒 | **Never run.** Needs a registered project and credentials; see `docs/EARTH_ENGINE_COMPARISON.md` |
| Earth Duet feature in the UI | ❌ | Still a planned stub by design |
