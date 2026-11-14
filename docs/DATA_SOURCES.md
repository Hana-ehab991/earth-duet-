# Data sources

| Purpose | Source | Access | Credentials | Verified here? |
|---|---|---|---|---|
| Historical temperature | NASA POWER, `T2M`, monthly point API (`/api/temporal/monthly/point`), community `AG` — https://power.larc.nasa.gov/docs/services/api/ | `scripts/fetch_historical.py` | none | **No** (host unreachable in build sandbox; response format follows public docs; builder unit-tested on a synthetic payload) |
| Satellite imagery | NASA GIBS WMTS (EPSG:3857, `MODIS_Terra_CorrectedReflectance_TrueColor`, GoogleMapsCompatible_Level9) — https://nasa-gibs.github.io/gibs-api-docs/ ; browse in https://worldview.earthdata.nasa.gov/ | Browser loads tiles directly | none | **No** — start date 2000-02-24 is from public docs; per-date tile availability is only discovered at runtime |
| Future projections | NASA NEX-GDDP-CMIP6 `tas` — https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6 | `scripts/fetch_projections.py --backend s3` (public bucket `nex-gddp-cmip6`) or `--backend ee` | none (s3) / Earth Engine (ee) | **No** |
| 3D globe | CesiumJS; base map = bundled Natural Earth II (no token) | npm | none | Yes (renders) |
| Audio | Tone.js | npm | none | Yes (state machine); audible output not verified |

Models used (edit `MODELS` in `scripts/fetch_projections.py`): ACCESS-CM2, CanESM5, MPI-ESM1-2-HR, MRI-ESM2-0, NorESM2-MM (variant r1i1p1f1, grid `gn`). **Confirm each exists with those labels in the catalog before a production run**; missing files fail loudly and nothing is guessed.

Attribution shown in-app: GIBS/ESDIS credit, POWER and NEX-GDDP-CMIP6 source names, Cesium credit. No NASA logos are used; no endorsement is implied.

Mandatory provenance per record is enforced by `backend/app/schemas/datasets.py` (location, geometry, variable, unit, source, processing, record type, baseline; projections add scenarios, models, windows, spread).
