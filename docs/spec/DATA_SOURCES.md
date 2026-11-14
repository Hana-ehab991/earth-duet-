# Data sources and integration requirements

## Historical temperature: NASA POWER
https://power.larc.nasa.gov/
https://power.larc.nasa.gov/docs/services/api/
Use a verified near-surface air temperature parameter such as T2M, with documented temporal aggregation, units, coverage, spatial support, and missing-value handling. NASA POWER products may derive from reanalysis/model-assisted sources; describe them accurately rather than calling every value a direct observation.

## Historical satellite imagery: NASA GIBS / Worldview
https://nasa-gibs.github.io/gibs-api-docs/
https://worldview.earthdata.nasa.gov/
Verify available layer names, imagery dates, projections, licensing/attribution, and tile integration. Imagery may not be available for every year. Imagery is separate from numerical temperature values.

## Future climate projections: NASA NEX-GDDP-CMIP6
https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6
Use `tas` with explicit Kelvin-to-Celsius conversion as needed, identified model(s), SSP2-4.5 and SSP5-8.5, and a stated multi-year averaging window for 2030, 2050, 2075 and 2100 (clip windows to available coverage). Explain model grid resolution and differences from historical NASA POWER values. Do not splice the two products without a justified baseline/anomaly approach.

## 3D globe: CesiumJS
https://cesium.com/learn/cesiumjs-learn/
Use CesiumJS with appropriate imagery source, correct token handling and fallback behavior.

## Audio: Tone.js
https://tonejs.github.io/
Use browser-user-gesture audio activation and fixed-scale, documented sonification mappings.

## Processing
Google Earth Engine (if access is configured): https://developers.google.com/earth-engine
Python: pandas, xarray, NumPy; geospatial libraries as needed.

## Mandatory provenance per record
location, analysis geometry, variable, value, unit, time range, source, processing method, type (observation/reanalysis/model historical/projection), and for projections: scenario, model, baseline and uncertainty where available.

## Credentials
Never commit or upload private API keys or .env secrets. Provide .env.example only.
