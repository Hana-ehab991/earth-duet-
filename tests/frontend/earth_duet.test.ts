import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  ASWAN, CAIRO, EMPTY_SELECTION, applyGlobePoint, applyManual, buildRequest, buildRows, canCompare, clearSlot, parseCoordinate, round4, sameLocation, summarize, validateComparison, viewForPair,
} from '../../frontend/src/features/earthDuet/logic'
import { FIXED_DOMAIN, colorForValue, fittedDomain, midiToHz, midiToNoteName, valueToMidi } from '../../frontend/src/features/earthDuet/sonify'

// A REAL response from the verified Phase 3 backend (Cairo vs Aswan, MODIS NDVI 2010-2024).
const real = JSON.parse(readFileSync(new URL('./fixtures/cairo_aswan_response.json', import.meta.url), 'utf-8'))
const clone = () => JSON.parse(JSON.stringify(real))

describe('parseCoordinate', () => {
  it('accepts plain decimals and rounds to 4 places', () => {
    expect(parseCoordinate('30.04444', 'lat')).toEqual({ ok: true, value: 30.0444 })
    expect(parseCoordinate(' -24 ', 'lat')).toEqual({ ok: true, value: -24 })
    expect(parseCoordinate('31,2357', 'lon')).toEqual({ ok: true, value: 31.2357 })
  })
  it('rejects bad input', () => {
    for (const t of ['', '  ', 'abc', '1e3', '30.0.1', '30,000,1', 'NaN', 'Infinity', '12°', '--5']) expect(parseCoordinate(t, 'lat').ok).toBe(false)
  })
  it('enforces ranges', () => {
    expect(parseCoordinate('90.0001', 'lat').ok).toBe(false)
    expect(parseCoordinate('-91', 'lat').ok).toBe(false)
    expect(parseCoordinate('180', 'lon').ok).toBe(true)
    expect(parseCoordinate('180.1', 'lon').ok).toBe(false)
  })
  it('never returns negative zero', () => {
    const r = parseCoordinate('-0', 'lat')
    expect(r.ok && Object.is(r.value, -0)).toBe(false)
    expect(Object.is(round4(-0.00001), -0)).toBe(false)
  })
})

describe('selection rules', () => {
  it('first click sets A, second sets B, third is ignored with a message', () => {
    let r = applyGlobePoint(EMPTY_SELECTION, { lat: 30.04441, lon: 31.23571 })
    expect(r.sel.a).toEqual(CAIRO)
    r = applyGlobePoint(r.sel, { lat: 24.0889, lon: 32.8998 })
    expect(r.sel.b).toEqual(ASWAN)
    const r3 = applyGlobePoint(r.sel, { lat: 10, lon: 10 })
    expect(r3.changed).toBe(false)
    expect(r3.sel).toEqual(r.sel)
    expect(r3.message).toMatch(/Change/)
  })
  it('an armed slot is replaced, then disarmed', () => {
    const sel = { a: CAIRO, b: ASWAN, armed: 'A' as const }
    const r = applyGlobePoint(sel, { lat: 10, lon: 20 })
    expect(r.sel.a).toEqual({ latitude: 10, longitude: 20 })
    expect(r.sel.b).toEqual(ASWAN)
    expect(r.sel.armed).toBeNull()
  })
  it('rejects a miss, NaN and out-of-range clicks without changing anything', () => {
    for (const p of [null, { lat: NaN, lon: 1 }, { lat: 91, lon: 0 }, { lat: 0, lon: 181 }]) {
      const r = applyGlobePoint(EMPTY_SELECTION, p)
      expect(r.changed).toBe(false)
      expect(r.sel).toEqual(EMPTY_SELECTION)
      expect(r.message).toBeTruthy()
    }
  })
  it('B may not equal A after 4-decimal rounding', () => {
    const r = applyGlobePoint({ a: CAIRO, b: null, armed: null }, { lat: 30.04444, lon: 31.23566 })
    expect(r.changed).toBe(false)
    expect(sameLocation(CAIRO, { latitude: 30.04444, longitude: 31.23566 })).toBe(true)
  })
  it('manual entry validates and reports the first problem', () => {
    expect(applyManual(EMPTY_SELECTION, 'A', '95', '10').changed).toBe(false)
    expect(applyManual(EMPTY_SELECTION, 'A', '10', 'x').changed).toBe(false)
    const ok = applyManual(EMPTY_SELECTION, 'B', '24.0889', '32.8998')
    expect(ok.sel.b).toEqual(ASWAN)
  })
  it('clear removes one slot only; compare needs two different points', () => {
    const sel = { a: CAIRO, b: ASWAN, armed: null }
    expect(canCompare(sel)).toBe(true)
    const c = clearSlot(sel, 'B')
    expect(c.a).toEqual(CAIRO); expect(c.b).toBeNull(); expect(canCompare(c)).toBe(false)
    expect(canCompare({ a: CAIRO, b: CAIRO, armed: null })).toBe(false)
  })
  it('builds exactly the documented request payload', () => {
    expect(buildRequest(CAIRO, ASWAN)).toEqual({
      locationA: { latitude: 30.0444, longitude: 31.2357 }, locationB: { latitude: 24.0889, longitude: 32.8998 },
      variable: 'ndvi', startYear: 2010, endYear: 2024, radiusKm: 10,
    })
  })
  it('viewForPair centres between the points with a sane height', () => {
    const v = viewForPair(CAIRO, ASWAN)
    expect(v.lat).toBeCloseTo(27.0667, 3)
    expect(v.height).toBeGreaterThanOrEqual(1_500_000)
    expect(v.height).toBeLessThanOrEqual(25_000_000)
  })
})

describe('validateComparison (real backend response)', () => {
  it('accepts the real Cairo/Aswan response', () => { expect(validateComparison(real).ok).toBe(true) })
  it('refuses synthetic or non-Earth-Engine data', () => {
    const s = clone(); s.isSynthetic = true; expect(validateComparison(s).ok).toBe(false)
    const o = clone(); o.dataOrigin = 'demo'; expect(validateComparison(o).ok).toBe(false)
  })
  it('refuses malformed payloads', () => {
    expect(validateComparison(null).ok).toBe(false)
    expect(validateComparison([]).ok).toBe(false)
    const a = clone(); a.locationA.observations[0].value = 'x'; expect(validateComparison(a).ok).toBe(false)
    const b = clone(); b.locationB.observations[0].value = 7; expect(validateComparison(b).ok).toBe(false)
    const c = clone(); c.locationA.observations.push({ ...c.locationA.observations[0] }); expect(validateComparison(c).ok).toBe(false)
    const d = clone(); delete c.provenance; delete d.provenance; expect(validateComparison(d).ok).toBe(false)
  })
})

describe('rows and statistics', () => {
  const data = validateComparison(real)
  if (!data.ok) throw new Error('fixture invalid')
  it('has 15 comparable rows with the exact observed values and no invented data', () => {
    const rows = buildRows(data.data)
    expect(rows).toHaveLength(15)
    expect(rows[0]).toMatchObject({ year: 2010, a: 0.21366, b: 0.11094 })
    expect(rows[0].diff).toBeCloseTo(0.10272, 10)
    expect(rows[14]).toMatchObject({ year: 2024, a: 0.18221, b: 0.112 })
  })
  it('summary uses only real values', () => {
    const s = summarize(buildRows(data.data))
    expect(s.a.n).toBe(15); expect(s.b.n).toBe(15); expect(s.comparableCount).toBe(15)
    expect(s.aHigherYears).toBe(15)
    expect(s.a.max).toEqual({ year: 2011, value: 0.21718 })
    expect(s.a.min).toEqual({ year: 2024, value: 0.18221 })
    expect(s.a.slopePerYear as number).toBeLessThan(0)
    expect(s.missingA).toEqual([]); expect(s.missingB).toEqual([])
  })
  it('missing values stay null: no interpolation, no difference', () => {
    const m = clone()
    m.locationA.observations[3].value = null
    m.locationB.observations = m.locationB.observations.filter((o: { year: number }) => o.year !== 2015)
    const v = validateComparison(m); if (!v.ok) throw new Error('should validate')
    const rows = buildRows(v.data)
    const r2013 = rows.find((r) => r.year === 2013)!
    expect(r2013.a).toBeNull(); expect(r2013.diff).toBeNull(); expect(r2013.b).not.toBeNull()
    const r2015 = rows.find((r) => r.year === 2015)!
    expect(r2015.b).toBeNull(); expect(r2015.diff).toBeNull()
    const s = summarize(rows)
    expect(s.comparableCount).toBe(13); expect(s.missingA).toEqual([2013]); expect(s.missingB).toEqual([2015])
  })
  it('handles an all-missing series', () => {
    const m = clone(); for (const o of m.locationA.observations) o.value = null
    const v = validateComparison(m); if (!v.ok) throw new Error('should validate')
    const s = summarize(buildRows(v.data))
    expect(s.a.n).toBe(0); expect(s.a.mean).toBeNull(); expect(s.comparableCount).toBe(0); expect(s.meanDiff).toBeNull()
  })
})

describe('sound and colour mapping', () => {
  it('is monotonic, deterministic and clamps with a report', () => {
    expect(valueToMidi(0, FIXED_DOMAIN)).toBe(48)
    expect(valueToMidi(0.8, FIXED_DOMAIN)).toBe(72)
    expect(valueToMidi(0.2, FIXED_DOMAIN)).toBeLessThan(valueToMidi(0.21, FIXED_DOMAIN))
    expect(valueToMidi(5, FIXED_DOMAIN)).toBe(72)
    expect(valueToMidi(-1, FIXED_DOMAIN)).toBe(48)
    expect(valueToMidi(0.3, FIXED_DOMAIN)).toBe(valueToMidi(0.3, FIXED_DOMAIN))
  })
  it('converts midi to Hz and note names (A4 = 440, C3 = 130.81)', () => {
    expect(midiToHz(69)).toBeCloseTo(440, 6)
    expect(midiToHz(48)).toBeCloseTo(130.81, 2)
    expect(midiToNoteName(69)).toBe('A4'); expect(midiToNoteName(48)).toBe('C3')
  })
  it('fitted domain spans the data and survives a flat series', () => {
    const d = fittedDomain([0.11, 0.2, 0.18])
    expect(d.min).toBe(0.11); expect(d.max).toBe(0.2); expect(d.mode).toBe('fitted')
    const flat = fittedDomain([0.3, 0.3])
    expect(flat.max).toBeGreaterThan(flat.min)
    expect(Number.isFinite(valueToMidi(0.3, flat))).toBe(true)
    expect(fittedDomain([])).toEqual(FIXED_DOMAIN)
  })
  it('missing value gets no colour; equal values get equal colour; higher NDVI differs', () => {
    expect(colorForValue(null, FIXED_DOMAIN)).toBeNull()
    expect(colorForValue(0.2, FIXED_DOMAIN)!.hex).toBe(colorForValue(0.2, FIXED_DOMAIN)!.hex)
    expect(colorForValue(0.2, FIXED_DOMAIN)!.hex).not.toBe(colorForValue(0.6, FIXED_DOMAIN)!.hex)
    expect(colorForValue(0.9, FIXED_DOMAIN)!.clamped).toBe('above')
  })
})

describe('architecture boundaries', () => {
  const walk = (dir: string): string[] => readdirSync(dir).flatMap((f) => { const p = join(dir, f); return statSync(p).isDirectory() ? walk(p) : [p] })
  const src = new URL('../../frontend/src/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
  const imports = (file: string) => [...readFileSync(file, 'utf-8').matchAll(/from\s+'([^']+)'/g)].map((m) => m[1])
  it('Earth Duet and Time Travel never import each other', () => {
    for (const f of walk(join(src, 'features', 'earthDuet'))) for (const i of imports(f)) expect(i).not.toMatch(/timeTravel/)
    for (const f of walk(join(src, 'features', 'timeTravel'))) for (const i of imports(f)) expect(i).not.toMatch(/earthDuet/)
  })
  it('core never imports features', () => {
    for (const f of walk(join(src, 'core')).filter((x) => /\.tsx?$/.test(x))) for (const i of imports(f)) expect(i).not.toMatch(/features\//)
  })
})
