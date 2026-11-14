# Location comparison with Google Earth Engine (NDVI)

> **Status: Phase 3 of 8 (backend comparison API + SQLite cache) on top of the Phase 2 data service. Reachable through the API only, not from the UI.**
> The Earth Engine integration has **never been run against the live service** (the build sandbox has no access to it).
> It is unit-tested with a mocked `ee` module only. Do not describe it as working with real data until the checklist at
> the end of this file has been completed on a machine with Earth Engine access. The Earth Duet feature stays registered as
> *planned*.

Phase 3 (this file, section 6 onwards) added the `POST /api/compare-locations` endpoint, the status endpoint and the SQLite cache.
Later phases add globe selection (4), the Earth Duet page (5), NDVI color and sound adapters (6) and the *Hear the Difference*
challenge (7).

## 1. What this phase adds

| File | Purpose |
|---|---|
| `backend/app/services/comparison_errors.py` | Structured errors (`{"error":{"code","message","hint"}}`) and HTTP status per code |
| `backend/app/services/comparison_settings.py` | Env-based settings (project, timeout, concurrency). Reads no credentials |
| `backend/app/services/comparison_validation.py` | Coordinate / radius / year / variable validation, pair checks |
| `backend/app/services/ndvi_processing.py` | Methodology constants, scaling, quality rules, annual processing, suitability (pure Python) |
| `backend/app/services/earth_engine_service.py` | Lazy `ee` import, ADC authentication, one server-side computation per region, concurrency/timeouts, error mapping |
| `tests/backend/test_comparison_*.py`, `test_ndvi_processing.py`, `test_earth_engine_service.py` | Unit tests (mocked Earth Engine) |

Existing files changed: `backend/requirements.txt` (+`earthengine-api`), `.env.example` (placeholders only), `.gitignore`
(cache directory and credential-like files). No existing source file was edited.

## 2. Scientific methodology (NDVI)

* **Dataset:** `MODIS/061/MOD13Q1` (Terra Vegetation Indices, 16-day, 250 m), DOI 10.5067/MODIS/MOD13Q1.061, catalog
  <https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1>. Band `NDVI`, stored as integers, **scale 0.0001**,
  catalog valid range −2000..10000, i.e. NDVI **−0.2 … 1.0**. Values outside that range (including the −3000 fill value) are
  discarded.
* **Quality filtering (per composite pixel).** Kept only if `SummaryQA == 0` (good data) **and** `DetailedQA` bits 8 (adjacent
  cloud), 10 (mixed clouds), 14 (possible snow/ice) and 15 (possible shadow) are all 0. The bit meanings were checked against the
  catalog page above.
* **Temporal aggregation.** For each year, composites whose start date is in `[April 1, June 1)` (end exclusive; Earth Engine
  `filterDate` semantics). Per pixel: mean of the valid composites. Regional value: mean over pixels (each pixel has equal weight).
  A composite starting late in the window can extend a few days beyond June 1.
* **Spatial support.** Circle of radius `radius_km` (default 10 km, allowed 1–25 km) around the point, evaluated at 250 m in the
  dataset's own sinusoidal grid. Both locations in a comparison use identical radius, years, variable, season, filters and
  thresholds (`validate_pair` rejects anything else).
* **Acceptance rules (design choices, documented and part of the cache fingerprint).** A year is reported only if ≥ 50 % of the
  region's pixels have a valid observation and valid pixels average ≥ 2 valid composites. Otherwise the year is **`null` with a
  reason code** (`no_composites`, `water`, `snow_ice`, `cloud`, `no_valid_observations`, `insufficient_valid_pixels`,
  `insufficient_valid_composites`, `no_pixels`). Nothing is interpolated or gap-filled.
* **Oceans and water.** Water is detected from the `DetailedQA` land/water flag of one reference composite (flags 0, 3, 5, 6, 7).
  ≥ 50 % water → status `unsuitable`, every year `null` (reason `water`). 10–50 % → warning `includes_water`.
* **Snow and cloud.** Snow/ice and cloud/shadow flagged pixels are excluded. The per-year flagged fractions are returned so a
  `snow_ice` or `cloud` reason is traceable. If no year survives, the region status is `unavailable`.
* **Other warnings:** `sparse_vegetation` (median NDVI < 0.2: bare ground, sand, rock, snow or built-up land likely, so small
  differences are noise-dominated), `negative_ndvi` (legitimate over water/snow/cloud; not "less vegetation" in a linear sense),
  `missing_years`, `southern_hemisphere_season`, `high_latitude_season`, and for pairs `regions_overlap`.
* **Wording rule.** NDVI is a greenness indicator from red/near-infrared reflectance. It is **not** a measurement of vegetation area,
  biomass, desertification or vegetation loss, and no text in the app may describe it that way.
* **Known limitations.** No land-cover classification (cropland, built-up land and natural vegetation are averaged together; a 10 km
  circle around a large city is largely built-up); one fixed April–June window at every latitude; water detected from one
  composite; interannual differences can reflect rainfall, phenology timing, compositing and aerosol/cloud residue rather than
  land-surface change; coordinates are rounded to 4 decimals (~11 m).
* **Request limits (cost protection).** One variable, radius 1–25 km, years 2010–2024 (max 15), future years rejected
  (no validated NDVI projection exists), at most `EARTH_DUET_EE_MAX_CONCURRENT` (default 4) computations in flight, at most
  `EARTH_DUET_EE_QUEUE_WAIT_S` seconds waiting for a slot (else `earth_engine_busy`, HTTP 429), at most
  `EARTH_DUET_EE_TIMEOUT_S` seconds per computation (else `earth_engine_timeout`, HTTP 504). A timed-out computation keeps its slot
  until Earth Engine actually finishes it, so timeouts cannot pile up load. Per-client **rate limiting** is added at the API layer in
  Phase 3.

## 3. Authentication and permissions (server side only)

The frontend never sees credentials and the user needs no Google account. **No service-account key files are created, read or
committed by this project.**

### Deployment (recommended): attached service identity + Application Default Credentials
1. Create or choose a Google Cloud project and **register it for Earth Engine** (<https://console.cloud.google.com/earth-engine>).
   Earth Engine is free for research, education and nonprofit use; commercial use is paid. Check which applies to your deployment
   and do not assume quota is unlimited.
2. Enable the Earth Engine API: `gcloud services enable earthengine.googleapis.com --project=PROJECT_ID`.
3. Run the backend with an **attached service account** (Cloud Run, Compute Engine, GKE, with workload identity where applicable).
4. Grant that service account, on the project: **Earth Engine Resource Viewer** (`roles/earthengine.viewer`) and **Service Usage
   Consumer** (`roles/serviceusage.serviceUsageConsumer`). Role names are from Google's Earth Engine access-control and
   service-account docs; confirm them in your IAM console.
5. Set `EE_PROJECT=PROJECT_ID` in the service environment. The code calls `google.auth.default(scopes=[earthengine,
   cloud-platform])` and `ee.Initialize(credentials=..., project=EE_PROJECT)`.

### Local development (Windows or any OS)
Either:
```
backend\.venv\Scripts\earthengine authenticate
backend\.venv\Scripts\earthengine set_project YOUR_PROJECT_ID
```
or `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/earthengine,https://www.googleapis.com/auth/cloud-platform`.
Then add `EE_PROJECT=YOUR_PROJECT_ID` to `backend\.env` (the setup script does not create this line). The service tries ADC first and
falls back to credentials stored by `earthengine authenticate`.
Do **not** point `GOOGLE_APPLICATION_CREDENTIALS` at a key file that lives inside the repository.

### Error codes
| Code | HTTP | Meaning |
|---|---|---|
| `earth_engine_not_configured` | 503 | package, project or credentials missing |
| `earth_engine_auth_failed` | 503 | credentials rejected or missing IAM roles / registration |
| `earth_engine_unavailable` | 503 | network / service outage |
| `earth_engine_dataset_unavailable` | 503 | catalog entry missing or inaccessible |
| `earth_engine_computation_limit` | 503 | service limit hit (try a smaller radius) |
| `earth_engine_timeout` | 504 | no answer within `EARTH_DUET_EE_TIMEOUT_S` |
| `earth_engine_quota_exceeded` / `earth_engine_busy` | 429 | quota/rate limit, or the local concurrency limit |
| `earth_engine_bad_response` | 502 | payload failed structural or physical-range checks (for example NDVI outside −0.2..1.0) |
| `earth_engine_error` | 502 | unclassified Earth Engine error |
| `invalid_coordinates`, `invalid_radius`, `invalid_year_range`, `unsupported_variable`, `identical_locations`, `mismatched_spatial_support` | 422 | invalid input |

On any failure the service raises; it never returns substitute, cached-as-live, interpolated or synthetic values.

## 4. Verification status

| Item | Status |
|---|---|
| Validation, scaling, QA rules, annual processing, suitability, error mapping, concurrency/timeout behaviour | Unit-tested with mocks (35 tests) |
| Dataset ID, band names, scale factor, valid range, QA bit meanings | Checked against the Earth Engine catalog page |
| ADC / project / IAM approach | Checked against Google's Earth Engine authentication and service-account docs |
| The server-side computation graph (`reduceRegion` parameters, `ee.Algorithms.If` for empty seasons, `crs` taken from the source image's projection, result key names) | **Not run against Earth Engine.** It is the most likely place for a first-run error |
| Real values, latency, quota behaviour | **Not verified** |

**Live verification checklist (needs a machine with Earth Engine access):** run `probe()`; fetch two known locations and compare the
regional NDVI with an independent calculation in the Earth Engine Code Editor; confirm the total-pixel count is close to
π·r²/(250 m)² ≈ 5,030 for a 10 km radius (the region is sampled on a 250 m grid); confirm an ocean point returns `unsuitable`; record typical latency.

## 5. Reverting Phase 2
Delete the five `comparison_*.py` / `ndvi_processing.py` / `earth_engine_service.py` files under `backend/app/services/`, the three
test files above, and this document; remove the `earthengine-api` line from `backend/requirements.txt` and the "Location comparison"
blocks appended to `.env.example` and `.gitignore`. No existing file was otherwise modified, no data file was touched.


---

# Phase 3: comparison API and persistent cache

> **Verification status.** Unit-tested with a **mocked** Earth Engine client only. **No real Earth Engine request has ever been
> made by this code**, so live behaviour (authentication, the computation graph, values, latency, quota) is **unverified**. The
> `GET /api/comparison/status` endpoint reports `configured_unverified` until a real request succeeds in the running process.

## 6. What Phase 3 adds

| File | Purpose |
|---|---|
| `backend/app/api/comparison_routes.py` | `POST /api/compare-locations`, `GET /api/comparison/status` |
| `backend/app/schemas/comparison.py` | Typed request (docs only) and response models, camelCase |
| `backend/app/services/location_comparison.py` | Orchestration: validate, cache, fetch (Phase 2 client), assemble |
| `backend/app/services/comparison_cache.py` | SQLite cache |
| `backend/app/services/comparison_api_settings.py` | Cache path/TTL, deadline, rate limit, body limit (env) |
| `backend/app/services/rate_limit.py` | Process-local sliding-window limiter |
| `tests/backend/test_comparison_cache.py`, `test_location_comparison.py`, `test_comparison_api.py`, `comparison_fakes.py` | Tests with a mocked Earth Engine |

Existing files edited: `backend/app/main.py` (register router, allow `POST` in CORS, one `ComparisonError` handler),
`.env.example` (commented variables), this document. Nothing in Phase 2, the frontend, the datasets or the `.bat` files changed.

## 7. API

### `POST /api/compare-locations`
Request (camelCase). `locationA`, `locationB`, `startYear`, `endYear` are required. `variable` defaults to `"ndvi"` and `radiusKm`
to `10`. Unknown fields are rejected so typos (`radius_km`) are not silently ignored.
```json
{
  "locationA": {"latitude": 30.0444, "longitude": 31.2357},
  "locationB": {"latitude": 24.0889, "longitude": 32.8998},
  "variable": "ndvi", "startYear": 2010, "endYear": 2024, "radiusKm": 10
}
```
Limits: radius 1-25 km, years 2010-2024 (inclusive), one variable, body at most 8 KiB (configurable). Coordinates are rounded to
4 decimals (section 9); the rounded value is what is analysed and reported (`requestedLatitude/Longitude` echo what was sent).
Identical locations (after rounding) are rejected; **overlapping regions are allowed with a `regions_overlap` warning**.

Response, **schema only: the placeholders are not measurements**:
```json
{
  "variable": "ndvi", "unit": "dimensionless (NDVI indicator)", "startYear": 2010, "endYear": 2024, "radiusKm": 10.0,
  "dataStatus": "live | cached | partially_cached",
  "dataOrigin": "earth_engine", "isSynthetic": false,
  "resultStatus": "complete | partial_data | no_usable_data",
  "resultMessage": "<text>",
  "comparableYears": ["<years where BOTH locations have a valid value>"],
  "locationA": {
    "latitude": 30.0444, "longitude": 31.2357, "requestedLatitude": 30.0444, "requestedLongitude": 31.2357,
    "dataStatus": "live | cached", "retrievedAt": "<ISO 8601 UTC, when Earth Engine was queried>",
    "earthEngineApiVersion": "<string or null>",
    "cache": {"status": "hit | miss | disabled", "key": "<sha256>", "expiresAt": "<ISO or null>",
              "canonicalLatitude": "30.0444", "canonicalLongitude": "31.2357"},
    "suitability": {"status": "ok | warning | unsuitable | unavailable", "waterFraction": "<0..1 or null>",
                    "totalPixels": "<int>", "waterPixels": "<int>"},
    "hasUsableData": "<bool>", "validYearCount": "<int>",
    "warnings": [{"code": "<e.g. sparse_vegetation>", "message": "<text>"}],
    "observations": [
      {"year": 2010, "value": "<NDVI number, or null>", "qualityStatus": "valid | unavailable",
       "reasonCode": "<null when valid; e.g. no_composites, water, snow_ice, cloud, insufficient_valid_pixels>",
       "reason": "<text or null>", "compositeCount": "<int>", "validPixelFraction": "<or null>",
       "meanValidComposites": "<or null>", "snowFlagFraction": "<or null>", "cloudFlagFraction": "<or null>"}
    ]
  },
  "locationB": {"...": "same structure as locationA"},
  "comparisonWarnings": [{"code": "regions_overlap | one_location_without_data | no_usable_data", "message": "<text>"}],
  "provenance": {"datasetId": "MODIS/061/MOD13Q1", "datasetVersion": "061", "sourceUrl": "...", "doi": "...", "producer": "...",
                 "band": "NDVI", "processingVersion": "ndvi-annual-v1", "configFingerprint": "<hash>",
                 "retrievedAt": "<earliest of the two locations>", "servedAt": "<ISO>"},
  "methodology": {"processingVersion": "...", "band": "NDVI", "scaleFactor": 0.0001, "unit": "...", "physicalRange": [-0.2, 1.0],
                  "seasonalWindow": {"start": "04-01", "endExclusive": "06-01"},
                  "qualityFiltering": "...", "temporalAggregation": "...", "spatialAggregation": "...",
                  "acceptanceRules": "...", "limitations": ["..."]}
}
```
**Valid request, no usable measurements (e.g. open ocean, persistent cloud or snow).** This is **HTTP 200** with
`resultStatus: "no_usable_data"`, every `value` null with its `reasonCode`, `suitability.status` and warnings. Exactly one location
without data gives `partial_data`. **HTTP errors are reserved** for invalid requests and genuine processing/service failures, so a
client can tell "this place has no usable NDVI" (200) from "the service failed" (4xx/5xx).

### `GET /api/comparison/status`
Cheap and read-only; never calls Earth Engine. Reports `configured` (EE project set and `earthengine-api` importable; **credentials
are not checked**), `earthEngine.status` (`not_configured`, `configured_unverified`, `last_request_succeeded`,
`last_request_failed`; the last two describe real requests handled by this process only), `cache` (enabled, accessible, entry
count, TTL), supported variables, years, radius range and request limits. No secrets or file paths.

### Errors (existing format `{"error": {"code", "message", "hint"}}`, lowercase codes)
Phase 2 codes keep their statuses (section 3). New in Phase 3:

| Code | HTTP | Meaning |
|---|---|---|
| `invalid_json` | 400 | body is not JSON |
| `invalid_request` | 422 | not an object, missing/unknown fields, wrong location shape |
| `request_too_large` | 413 | body over the limit |
| `rate_limited` | 429 | per-client limit; `Retry-After` header is set |
| `internal_error` | 500 | unexpected failure; details only in server logs |

`invalid_coordinates`, `invalid_radius`, `invalid_year_range`, `unsupported_variable`, `identical_locations` are 422. Provider
failures: `earth_engine_not_configured`/`_auth_failed` 503, `_timeout` 504, `_quota_exceeded`/`_busy` 429, `_bad_response` 502.
Provider text, stack traces and file paths are never returned; unclassified provider errors are logged and replaced by a generic hint.

## 8. Frontend integration notes (for Phase 4)
* This endpoint is camelCase; the older endpoints are snake_case. `frontend/src/core/api/client.ts` only has a GET helper, so Phase 4
  needs a POST helper that reuses `ApiRequestError`.
* Show `dataStatus`, `retrievedAt` and `resultStatus`. Treat `value: null` as a gap, never as zero. Show each location's `warnings`.
* Describe NDVI changes as changes in a greenness indicator, never as vegetation area or loss.

## 9. SQLite cache

File: `data/cache/comparison.sqlite` (git-ignored; override with `EARTH_DUET_COMPARISON_CACHE_PATH`). Created on first use. Separate
from `data/processed` and `data/demo`; the curated JSON is never read or written by it.

**Granularity.** One row per location; a comparison reads and writes two rows.

**Key** = SHA-256 of canonical JSON of: cache schema version; dataset ID and version; variable; canonical latitude and longitude
(fixed 4-decimal strings, `-0.0` normalised) and the coordinate precision; radius (fixed 3 decimals); start and end year; season
start and end; **config fingerprint** (QA filtering bits, scale factor, validity thresholds, water flags, nominal scale); processing
version. Any change gives a miss.

**Coordinate precision.** 0.0001 degree = about 11.1 m of latitude (11.1 m x cos(latitude) of longitude), against a source pixel of
about 231.7 m. The rounded coordinates are the ones Earth Engine analyses, so two requests share a row only if they analyse exactly
the same circle. Requests 0.0001 degree apart are different rows. Canonical coordinates are stored as columns and inside
`canonical_params`; the response returns them, together with what was requested.

**Table `region_results`**: `cache_key` (PK), `cache_schema_version`, `dataset_id`, `dataset_version`, `variable`, `latitude`,
`longitude`, `radius_km`, `start_year`, `end_year`, `season_start`, `season_end_exclusive`, `config_fingerprint`,
`processing_version`, `canonical_params`, `payload` (JSON of the validated Phase 2 result), `payload_sha256`, `origin`
(constrained to `earth_engine`: demo or synthetic rows cannot be stored), `retrieved_at`, `earth_engine_api_version`, `created_at`,
`expires_at`. Indexes: `expires_at`; (`dataset_id`, `variable`, `latitude`, `longitude`, `radius_km`, `start_year`, `end_year`).

**Behaviour.** Hit = unexpired row that passes verification (origin, schema version, canonical parameters, checksum, structure,
physical range, matching request, current methodology). Anything else is a miss; a failed row is deleted. Writes are one
`BEGIN IMMEDIATE` transaction (WAL mode, busy timeout), expired rows are purged on write. Errors are never stored. All-null results
(for example ocean) **are** stored: they are deterministic outcomes of real retrieved data. A cache hit keeps the original
`retrievedAt`. If the database is unreadable or locked, comparisons still work live and the cache is reported inaccessible.
Concurrent identical requests share one Earth Engine fetch per location (single flight, per process).

**Expiry/refresh.** `EARTH_DUET_COMPARISON_CACHE_TTL_DAYS` (default 30; `0` disables the cache). To force a refresh, delete the file.
Cached rows are never refreshed by a request parameter (that would let clients spend Earth Engine quota).

## 10. Configuration (environment or `backend/.env`)
| Variable | Default | Meaning |
|---|---|---|
| `EE_PROJECT` | none | Earth Engine project (Phase 2); required for live data |
| `EARTH_DUET_COMPARISON_CACHE_PATH` | `<data dir>/cache/comparison.sqlite` | cache file |
| `EARTH_DUET_COMPARISON_CACHE_TTL_DAYS` | 30 | 0 to 3650; 0 disables |
| `EARTH_DUET_COMPARISON_DEADLINE_S` | 120 | overall time per request (10-600) |
| `EARTH_DUET_COMPARISON_RATE_LIMIT` | 20 | requests per client per window; 0 disables |
| `EARTH_DUET_COMPARISON_RATE_WINDOW_S` | 60 | window length |
| `EARTH_DUET_TRUST_FORWARDED_FOR` | false | use the right-most `X-Forwarded-For` entry (trusted proxy only) |
| `EARTH_DUET_COMPARISON_MAX_BODY_BYTES` | 8192 | request body limit (1024-65536) |
| `EARTH_DUET_EE_TIMEOUT_S`, `_EE_MAX_CONCURRENT`, `_EE_QUEUE_WAIT_S` | 60 / 4 / 10 | Phase 2 limits |

## 11. Limitations
* **Rate limiting and single-flight are per process.** With several workers or instances each counts separately (the effective limit
  is about N times higher) and identical requests in different workers can each call Earth Engine. Behind a proxy, every client looks
  the same unless `EARTH_DUET_TRUST_FORWARDED_FOR` is enabled for a trusted proxy. This reduces accidental floods; it is not a security
  boundary. Use a gateway for real abuse protection.
* **SQLite on ephemeral or shared filesystems.** On Cloud Run or similar the file disappears with the instance and is not shared
  between instances. Several processes on one local disk are fine (WAL). Do not put the file on a network share.
* A request waits for Earth Engine synchronously (up to the deadline). There is no job polling.
* The Phase 2 limitations (single April-June window, no land-cover classification, water from one composite, NDVI is not vegetation
  area) apply unchanged and are returned in `methodology.limitations`.
* Live Earth Engine behaviour is unverified (see the checklist in section 4).

## 12. Windows: run and test
1. First time: double-click `setup-earth-duet.bat` (creates `backend\.venv`, installs requirements including `earthengine-api`).
2. Create `backend\.env` with `EE_PROJECT=your-registered-project-id`, then in a terminal in the project folder:
   `backend\.venv\Scripts\earthengine authenticate` (opens a browser; credentials stay on this machine).
3. Offline checks (no Earth Engine needed): `backend\.venv\Scripts\python -m pytest tests\backend -q`
4. Start with `start-earth-duet.bat` (API on http://127.0.0.1:8000, interactive docs at `/docs`).
5. PowerShell:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/comparison/status
$body = @{ locationA = @{latitude=30.0444; longitude=31.2357}; locationB = @{latitude=24.0889; longitude=32.8998};
           variable = "ndvi"; startYear = 2010; endYear = 2024; radiusKm = 10 } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/compare-locations -ContentType "application/json" -Body $body
```
The first call is live and slow; repeat it to see `dataStatus: "cached"`. Without credentials you should get HTTP 503
`earth_engine_not_configured` (a correct result, not a bug). The `.bat` files have never been run on Windows by the author.

## 13. Reverting Phase 3
Delete the seven files in section 6 (and `tests/backend/comparison_fakes.py`), delete `data/cache/`, and in `main.py` remove the
`comparison_router` and `ComparisonError`/`location_comparison` imports, the `app.state.comparison_service` line, the
`_comparison_error` handler, the `include_router(comparison_router)` line, and change `allow_methods` back to `["GET"]`. Remove the
Phase 3 block from `.env.example` and sections 6-13 of this file. Phase 2 and all existing features are unaffected.
