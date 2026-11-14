# Data methodology

## Historical (NASA POWER T2M)
* Point extraction at Cairo (30.0444°N, 31.2357°E). The value represents the containing POWER grid cell (documented as ~0.5° lat × 0.625° lon, MERRA-2 based — *verify against current POWER docs*). The box drawn on the globe is this nominal cell.
* Record type is **`reanalysis`** ("model-assisted"), never labelled "observation".
* Annual value = day-weighted mean of the 12 monthly means. **Any year with a missing month (fill value −999) is withheld (`null`)** instead of partially averaged. POWER's own `YYYY13` annual key is ignored (recomputed for transparency).
* The latest complete year is the "present". The unit must be `C`; any other unit aborts the build (no silent relabelling).
* Baseline: mean of annual T2M 1995–2014 from the same product; build fails if the baseline period is incomplete.

## Future (NEX-GDDP-CMIP6 `tas`)
* Daily `tas` (K) at the 0.25° cell containing Cairo; converted `T[°C] = T[K] − 273.15`.
* Target years 2030, 2050, 2075, 2100, each a **20-year climatological window centred on the target** (2030→2020–2039, 2050→2040–2059, 2075→2065–2084). The 2100 window would extend past the data end, so it is **clipped to 2090–2100 (11 years)** and flagged `clipped`.
* Aggregation: mean of all daily values in the window (both backends return `(mean_K, n_days)`).
* Baseline/anomaly: each model's own `historical` 1995–2014 mean; anomaly = window mean − that baseline. Ensemble = unweighted mean across the listed models; min/max/σ are **inter-model spread, not a confidence interval**.
* Scenarios SSP2-4.5 and SSP5-8.5 share location, models, window length and baseline, so comparisons are like-for-like. They are conditional projections, not forecasts.

## Keeping products distinguishable
POWER (reanalysis, 0.5°×0.625°) and NEX-GDDP (bias-corrected model, 0.25°) differ in grid, bias and nature. The app therefore: draws them as separate chart series (observed line, projection markers); never interpolates between them; shows a gap for years with no data; labels absolute values as not directly comparable; and offers an **anomaly view** (each product vs its own 1995–2014 baseline) for like-for-like change. No bias-adjustment/splicing is performed.

## Imagery
GIBS imagery is a single representative day per year (15 July) chosen to compare the same season; it can contain cloud or gaps. Years before 2000-02-24 or in the future are reported unavailable. Tile load failures are detected at runtime and the labelled base map remains. Imagery is visual context only; future years show a projected-climate overlay (the dataset's grid cell), never a future photograph.

## Availability honesty
`resolveYear()` (frontend) returns observed / projection / *unavailable* — it never interpolates. Gaps (e.g. 2026–2029, 2031–2049) show "No verified data" and sound is silent.
