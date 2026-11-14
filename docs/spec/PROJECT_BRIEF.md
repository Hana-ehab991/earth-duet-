# Earth Duet — Project Brief

Challenge: The Earth Information Jukebox (NASA Space Apps concept)

## Vision
Earth Duet turns Earth-science measurements into synchronized 3D maps, colors, audio, charts, and accessible text. The application is a multi-feature platform, **not** a standalone Time Travel demo.

## Feature 1 — Time Travel (implement first)
Explore past observations, the latest available observations, and conditional future climate projections on a 3D globe. A year selector synchronizes maps, measured/modelled values, charts, Color Symphony, and sonification.

MVP: Cairo, Egypt; annual near-surface air temperature. Historical NASA POWER T2M and future NASA NEX-GDDP-CMIP6 `tas` are different products and must not be joined into an apparently homogeneous series without a documented methodology. Future periods should use specified climatological windows and scenarios (SSP2-4.5, SSP5-8.5). Show future *climate overlays*, never invented future satellite photographs.

## Feature 2 — Earth Duet (later)
Two-region comparison using the same scientific variable, time alignment, and sound scale; listening challenge with chart reveal. Build extensible architecture but do not implement the full feature yet.

## Feature 3 — Color Symphony (shared engine, initial integration now; richer UX later)
Deterministic, accessible mapping of environmental values to color; sound and visual readouts remain synchronized. No color-only meaning.

## Architecture
Reusable globe, geospatial data adapters, data provenance, audio engine, color mapping, charting, and navigation. Feature-specific UI/state isolated; shared interfaces typed and documented. Avoid hard-coded assumptions about Cairo or temperature in shared services.

## Non-negotiables
No fabricated NASA values, dates, imagery, projections, citations, or claims of NASA endorsement. Clearly distinguish observed/reanalysis/model-historical/projection datasets; expose source, variable, units, spatial resolution, scenario, model, aggregation and baseline. Show missing-data states. Keyboard, screen-reader and mute controls. Real working code, tests, setup instructions, and IMPLEMENTATION_STATUS.md.
