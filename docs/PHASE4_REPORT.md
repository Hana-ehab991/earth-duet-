# Earth Duet – submission MVP: implementation and test report

Scope delivered (Phase 4 + essential Phase 5/6, frontend only): the Phase 3 backend, scientific method and cache are **unchanged**.

## What was added
* **Earth Duet tab** (`frontend/src/features/earthDuet/`): click the globe to set A then B (distinct cyan/amber markers with coordinates), change/clear/reset, validated manual lat/lon entry, "Cairo vs Aswan" preset, Fly-to buttons.
* **Compare button** → real `POST /api/compare-locations` (NDVI, 2010–2024, 10 km). Loading state with elapsed time, Cancel, structured backend errors, stale-result warning when A/B change.
* **Results**: A/B line charts, A−B difference chart, comparable years, missing-data and warning notices, summary statistics, accessible data table, provenance and method limitations. NDVI is labelled a dimensionless greenness indicator, not a vegetation percentage.
* **Duet**: Tone.js (existing dependency). One beat per year; A = triangle voice (left), B = sine voice (right); pitch = NDVI on a fixed 0–0.8 scale (or an optional "emphasise differences" fitted scale, clearly labelled). Missing year = silence.
* **Colour**: viridis (colour-blind safe) strips for A and B, synchronised with playback, same scale as the sound. Numbers are always shown beside colours.
* Safety: the response is refused if it is not `isSynthetic:false` and `dataOrigin:"earth_engine"`, or has malformed/out-of-range values. Missing values stay `null`; there is no interpolation or fill anywhere.

## Files changed (against the Phase 3 baseline)
Modified: `core/globe/GlobeEngine.ts`, `core/globe/EarthGlobe.tsx`, `core/api/client.ts` (all additive/opt-in; Time Travel passes no new props), `app/featureRegistry.ts` (Earth Duet badge "soon" → available), `start-earth-duet.bat`, `README.md`, `docs/PHASE4_REPORT.md` (new).
New: everything under `frontend/src/features/earthDuet/`, `tests/frontend/earth_duet.test.ts`, `tests/frontend/fixtures/cairo_aswan_response.json` (the real API response).
Not touched: `TimeTravelPage.tsx`, all of `features/timeTravel/`, `App.tsx`, `package.json`, lockfile, the whole backend.

## Tests – what was and was not run
| Check | Result |
|---|---|
| Earth Duet logic tests (25 cases: coordinates, selection rules, response validation, rows/statistics with the real response, missing-data handling, sound/colour mapping, import boundaries) | **Passed**, but run with Node's type-stripping and a minimal stand-in for `vitest`, because `npm install` is impossible in the build environment. Real `npm test` has NOT been run. |
| TypeScript on pure modules (`logic.ts`, `sonify.ts`, `types.ts`), strict mode | **Passed** (tsc 6.0.3). |
| TypeScript on all new/changed TSX, with third-party types stubbed | No errors other than stub artefacts. **Not equivalent to the real `npm run typecheck`.** |
| Syntax of every new/changed file (esbuild) | Passed. |
| `npm run typecheck`, `npm test` (real vitest, 28 old + new), `npm run build` | **NOT RUN** (no npm network access). |
| Backend pytest | **NOT RUN** (pytest not installed here; backend untouched). |
| Browser behaviour: Cesium clicks, markers, recharts rendering, Tone.js sound, layout, Time Travel regression | **NOT RUN / UNVERIFIED.** Needs the manual checklist below. |
| Live call to the real backend from the new UI | **NOT RUN.** |

## Manual checklist (Windows, about 5 minutes)
1. Time Travel tab: markers switch location, slider and imagery toggle work, globe drags/zooms.
2. Earth Duet tab: click globe → A appears, click again → B appears; third click shows a hint.
3. "Change A" then click globe moves A. Clear/Reset work. Typing `95` as latitude shows an error.
4. "Example: Cairo vs Aswan" → Compare → two lines (A ≈ 0.18–0.22, B ≈ 0.11), difference bars, B sparse-vegetation warning, provenance.
5. Play duet: you hear two voices, strips highlight the current year. Stop works.
6. Stop the backend, press Compare: a clear "Could not reach the Earth Duet API" message appears.

## Known limits
* Fixed comparison settings (NDVI, 2010–2024, 10 km); no sliders.
* A drag never places a point (Cesium behaviour, to be confirmed in browser).
* Globe clicks use the ellipsoid pick (same as the existing coordinate readout).
