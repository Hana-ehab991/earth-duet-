/**
 * Color Symphony engine — deterministic value → color mapping with FIXED domains.
 * Domains are supplied by the caller (variable reference range), never derived from the data being shown,
 * so colors are comparable across years, scenarios and locations.
 */
export interface ColorScale {
  id: string
  label: string
  kind: 'sequential' | 'diverging'
  stops: string[]
  domain: { min: number; max: number }
  /** diverging only: data value mapped to the neutral midpoint (default 0) */
  center?: number
  colorBlindSafe: boolean
  note: string
}

// Matplotlib 'plasma' and 'viridis' (perceptually uniform), ColorBrewer RdBu / PuOr (diverging).
export const PLASMA = ['#0d0887', '#46039f', '#7201a8', '#9c179e', '#bd3786', '#d8576b', '#ed7953', '#fb9f3a', '#fdca26', '#f0f921']
export const VIRIDIS = ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
export const RDBU = ['#2166ac', '#67a9cf', '#d1e5f0', '#f7f7f7', '#fddbc7', '#ef8a62', '#b2182b']
export const PUOR = ['#542788', '#998ec3', '#d8daeb', '#f7f7f7', '#fee0b6', '#f1a340', '#b35806']

export type Rgb = [number, number, number]
export const hexToRgb = (h: string): Rgb => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as Rgb
export const rgbToHex = ([r, g, b]: Rgb) => '#' + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')

function lerpStops(stops: string[], t: number): string {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(x))
  const f = x - i
  const a = hexToRgb(stops[i]), b = hexToRgb(stops[i + 1])
  return rgbToHex([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f])
}

/** Position 0..1 on the scale. Diverging scales are piecewise-linear around `center`. */
export function scalePosition(scale: ColorScale, value: number): number {
  const { min, max } = scale.domain
  if (scale.kind === 'diverging') {
    const c = scale.center ?? 0
    return value >= c ? 0.5 + (0.5 * (value - c)) / (max - c) : 0.5 - (0.5 * (c - value)) / (c - min)
  }
  return (value - min) / (max - min)
}

export interface ColorResult { hex: string; position: number; clamped: 'below' | 'above' | null }
export function colorAt(scale: ColorScale, value: number): ColorResult {
  const p = scalePosition(scale, value)
  const clamped = p < 0 ? 'below' : p > 1 ? 'above' : null
  const pc = Math.min(1, Math.max(0, p))
  return { hex: lerpStops(scale.stops, pc), position: pc, clamped }
}

export function legendTicks(scale: ColorScale, count = 5): { value: number; position: number }[] {
  const { min, max } = scale.domain
  return Array.from({ length: count }, (_, i) => {
    const value = min + ((max - min) * i) / (count - 1)
    return { value, position: Math.min(1, Math.max(0, scalePosition(scale, value))) }
  })
}

export const gradientCss = (scale: ColorScale) =>
  `linear-gradient(to right, ${scale.stops.map((c, i) => `${c} ${(i / (scale.stops.length - 1)) * 100}%`).join(', ')})`

/** Build the scale for a variable. `range` is the documented fixed range. */
export function getScale(kind: 'sequential' | 'diverging', range: { min: number; max: number }, colorBlind: boolean): ColorScale {
  if (kind === 'sequential')
    return colorBlind
      ? { id: 'viridis', label: 'Viridis (color-blind safe)', kind, stops: VIRIDIS, domain: range, colorBlindSafe: true, note: 'Perceptually uniform, readable with common color-vision deficiencies.' }
      : { id: 'plasma', label: 'Plasma (warm sequential)', kind, stops: PLASMA, domain: range, colorBlindSafe: false, note: 'Perceptually uniform sequential scale; lightness increases with value.' }
  return colorBlind
    ? { id: 'puor', label: 'Purple–orange (color-blind safe)', kind, stops: PUOR, domain: range, center: 0, colorBlindSafe: true, note: 'Diverging around 0; avoids red–green confusion.' }
    : { id: 'rdbu', label: 'Blue–red (diverging)', kind, stops: RDBU, domain: range, center: 0, colorBlindSafe: false, note: 'Diverging around 0 (no change vs. baseline).' }
}
