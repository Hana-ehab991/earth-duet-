# Architecture

```
frontend/src
  app/            shell, navigation, featureRegistry.ts   ← add a feature here
  core/           feature-agnostic, reusable
    api/          fetch client (typed errors, abort), shared dataset types, useAsyncResource (stale-request safe), useDebounced
    timeline/     createTimelineStore(): zustand factory — year, bounds, availableYears, playback, speed
    globe/        GlobeEngine (Cesium wrapper: fly-to, markers, tile overlay w/ error reporting, support rectangle) + EarthGlobe
    color/        Color Symphony: fixed-domain scales, palettes, ColorLegend
    audio/        AudioEngine, TemperatureSonifier, DataNormalizer, SoundMappingConfig, useSonifier, AudioControls
    settings/     a11y/display/audio preferences (persisted; audioEnabled never restored)
    provenance/   ProvenancePanel (renders any dataset following the shared schema)
    ui/           Panel, Badge, Notice
  features/
    timeTravel/   store, resolver (pure), chartData (pure), page + components   ← feature-specific state lives here only
    earthDuet/    planned stub          colorSymphony/ planned stub
backend/app       api/routes · schemas (provenance-first) · services (dataset_store, builders, climate_processing, imagery)
```

**Decoupling rules.** `core/` never imports from `features/`. The globe takes data as props (markers, tile overlay, colored rectangle) and knows nothing about temperature or Cairo. The audio engine is configured by a `SoundMappingConfig`. Each feature creates its **own** timeline store instance. The backend keys everything by `(location, variable)`; adding a location/variable means metadata + a processed file, not code (locations without a dataset return `dataset_not_configured` — Cairo data is never reused).

**Synchronization (Time Travel).** One timeline `year` → `resolveYear()` → `YearResolution` (observed | projection | unavailable) → a single `metricValue` that drives numbers, chart marker, globe rectangle color, legend marker, text summary and sound. Rapid slider moves: data is fetched once per location; imagery metadata is debounced (300 ms) and previous requests are aborted, so stale responses are ignored.

## Adding a feature
1. `frontend/src/features/<id>/<Name>Page.tsx` (own zustand store if needed).
2. Register it in `app/featureRegistry.ts`.
3. Reuse `core/*` (e.g. Earth Duet: two `createTimelineStore` instances or one shared; one `SoundMappingConfig` per region; `getScale` with a shared fixed domain).
4. New data: add metadata JSON + a script + schema entry; expose via an existing `/api/*` route.
