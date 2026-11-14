/**
 * Documented sonification mappings (see docs/SONIFICATION.md).
 * The pitch assigned to a value is an arbitrary, fixed design choice — NOT a physical property of temperature.
 */
export interface SoundMappingConfig {
  id: string
  label: string
  /** Fixed reference range used for normalization (never rescaled per year). */
  range: { min: number; max: number }
  unit: string
  /** Pitch: exponential (musical) mapping of normalized value across `octaves` above `baseFrequency`. */
  baseFrequency: number
  octaves: number
  /** Brightness: low-pass cutoff mapped linearly (log-spaced) with the normalized value. */
  filterMin: number
  filterMax: number
  waveform: 'sine' | 'triangle'
  /** Seconds to glide between successive values. */
  glideSeconds: number
  /** Peak linear gain before master volume (kept well below clipping). */
  peakGain: number
  description: string
}

export function temperatureMapping(range: { min: number; max: number }, unit = '°C'): SoundMappingConfig {
  return {
    id: 'temperature-pitch-v1', label: 'Temperature → pitch', range, unit,
    baseFrequency: 220, octaves: 2, filterMin: 700, filterMax: 4200, waveform: 'triangle', glideSeconds: 0.35, peakGain: 0.5,
    description: 'Value is clamped to the fixed reference range and normalized 0–1. Pitch rises exponentially from A3 (220 Hz) at the range minimum to A5 (880 Hz) at the maximum; a low-pass filter opens with the same value.',
  }
}
