import { describe, expect, it } from 'vitest'
import { colorAt, getScale, legendTicks, scalePosition } from '../../frontend/src/core/color/scales'
import { normalize } from '../../frontend/src/core/audio/DataNormalizer'
import { describeSound, frequencyToNoteName, valueToFilterHz, valueToFrequency } from '../../frontend/src/core/audio/mapping'
import { temperatureMapping } from '../../frontend/src/core/audio/SoundMappingConfig'

const range = { min: 15, max: 35 }
describe('Color Symphony', () => {
  it('is deterministic and uses the fixed domain (not rescaled per year)', () => {
    const s = getScale('sequential', range, false)
    expect(colorAt(s, 22.3)).toEqual(colorAt(s, 22.3))
    expect(colorAt(s, 15).hex).toBe('#0d0887'); expect(colorAt(s, 35).hex).toBe('#f0f921')
  })
  it('clamps and reports out-of-range values', () => {
    const s = getScale('sequential', range, false)
    expect(colorAt(s, 50)).toMatchObject({ clamped: 'above', position: 1 }); expect(colorAt(s, 0)).toMatchObject({ clamped: 'below', position: 0 })
  })
  it('color-blind palette differs', () => {
    expect(colorAt(getScale('sequential', range, true), 25).hex).not.toBe(colorAt(getScale('sequential', range, false), 25).hex)
  })
  it('diverging scale is neutral at 0 even with asymmetric domain', () => {
    const d = getScale('diverging', { min: -2, max: 7 }, false)
    expect(scalePosition(d, 0)).toBeCloseTo(0.5); expect(colorAt(d, 0).hex).toBe('#f7f7f7')
    expect(colorAt(d, -2).hex).toBe('#2166ac'); expect(colorAt(d, 7).hex).toBe('#b2182b')
  })
  it('legend ticks show real values', () => { expect(legendTicks(getScale('sequential', range, false), 5).map((t) => t.value)).toEqual([15, 20, 25, 30, 35]) })
})

describe('Sonification mapping', () => {
  const cfg = temperatureMapping(range)
  it('maps range ends to A3 and A5 exponentially', () => {
    expect(valueToFrequency(15, cfg)).toBeCloseTo(220); expect(valueToFrequency(35, cfg)).toBeCloseTo(880); expect(valueToFrequency(25, cfg)).toBeCloseTo(440)
    expect(frequencyToNoteName(440)).toBe('A4'); expect(frequencyToNoteName(220)).toBe('A3')
  })
  it('is monotonic, deterministic and bounded (no spikes)', () => {
    let prev = 0
    for (let v = 10; v <= 40; v += 0.5) { const f = valueToFrequency(v, cfg); expect(f).toBeGreaterThanOrEqual(prev); expect(f).toBeLessThanOrEqual(880.0001); prev = f }
    expect(valueToFilterHz(35, cfg)).toBeCloseTo(cfg.filterMax); expect(valueToFilterHz(15, cfg)).toBeCloseTo(cfg.filterMin)
  })
  it('normalization uses the fixed range and flags clamping', () => {
    expect(normalize(25, range)).toEqual({ n: 0.5, clamped: null }); expect(normalize(99, range).clamped).toBe('above')
  })
  it('text alternative exists for values and for missing data', () => {
    expect(describeSound(25, cfg)).toMatch(/A4.*440 Hz.*50%/); expect(describeSound(null, cfg)).toMatch(/Silent/)
    expect(describeSound(50, cfg)).toMatch(/above the reference range/)
  })
})
