# Sonification

Engine: `frontend/src/core/audio` — `AudioEngine` (Tone.js, lazy-loaded, gesture-started, Limiter at −6 dB, master gain), `TemperatureSonifier` (variable-agnostic), `DataNormalizer`, `SoundMappingConfig`, `mapping.ts` (pure functions), `useSonifier` (React binding), `AudioControls`.

## Mapping `temperature-pitch-v1` (deterministic)
1. **Normalize** the displayed value to 0–1 against a **fixed** reference range (never per-year): absolute temperature 15–35 °C; anomaly −2 to +7 °C (`data/metadata/variables.json`). Out-of-range values are clamped and reported in the text equivalent.
2. **Pitch** = 220 Hz × 2^(2·n): A3 at the minimum → A5 at the maximum (exponential = musically even steps).
3. **Brightness**: low-pass cutoff 700 → 4200 Hz (log-spaced) with the same n.
4. Triangle wave; glide 0.35 s; envelope ramps 0.15 s up / 0.6 s down; peak gain 0.5; volume taper `0.6·v²`, ramped 80 ms.
5. No verified data → fade to silence (no invented pitch).

The pairing of "hotter = higher" is a design convention. **No note is claimed to be inherent to a temperature.**

## Behaviour & safety
* Off by default; "Enable sound" must be pressed (browser autoplay rules). The enabled state is never restored from storage.
* A short "ping" on each year change, sustained while the timeline plays.
* Limiter, volume slider, mute, calibration example (low/middle/high of the range), "Listen to both" scenarios.
* Disposal: oscillator/filter/gain disposed on disable/unmount; the engine can `dispose()` fully.
* Non-audio alternative: always-visible text such as "Pitch A4 (440 Hz), 50% of the 15–35 °C reference range".
