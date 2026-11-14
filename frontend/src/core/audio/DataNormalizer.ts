export interface Normalized { n: number; clamped: 'below' | 'above' | null }

/** Normalize a value to 0..1 within a FIXED range. Out-of-range values are clamped and reported, never silently rescaled. */
export function normalize(value: number, range: { min: number; max: number }): Normalized {
  const raw = (value - range.min) / (range.max - range.min)
  return { n: Math.min(1, Math.max(0, raw)), clamped: raw < 0 ? 'below' : raw > 1 ? 'above' : null }
}
