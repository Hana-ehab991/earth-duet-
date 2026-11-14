import { describe, expect, it } from 'vitest'
import { allAvailableYears, metricValue, modeForYear, resolveYear } from '../../frontend/src/features/timeTravel/resolver'
import { buildChartRows } from '../../frontend/src/features/timeTravel/chartData'
import { makeObserved, makeProjection } from './fixtures'

const o = makeObserved(), p = makeProjection()
const r = (year: number, scenario = 'ssp245', obs: typeof o | null = o, prj: typeof p | null = p) => resolveYear({ year, observed: obs, projection: prj, scenario })

describe('resolveYear', () => {
  it('past observation with anomaly vs POWER baseline', () => {
    const x = r(2010); expect(x.kind).toBe('observed')
    if (x.kind === 'observed') { expect(x.mode).toBe('past'); expect(x.value).toBeCloseTo(21); expect(x.anomaly).toBeCloseTo(0.5) }
  })
  it('latest complete year is "present"', () => { const x = r(2025); expect(x.kind === 'observed' && x.mode).toBe('present') })
  it('incomplete year is unavailable with the stated reason — never a value', () => {
    const x = r(2000); expect(x.kind).toBe('unavailable'); if (x.kind === 'unavailable') expect(x.reason).toMatch(/11\/12/)
  })
  it('gap year between observations and first projection is unavailable and lists neighbours', () => {
    const x = r(2028); expect(x.kind).toBe('unavailable')
    if (x.kind === 'unavailable') { expect(x.previousYear).toBe(2025); expect(x.nextYear).toBe(2030); expect(x.reason).toMatch(/2030, 2050, 2075, 2100/) }
  })
  it('before the record and in the far gap are unavailable', () => { expect(r(1985).kind).toBe('unavailable'); expect(r(2060).kind).toBe('unavailable') })
  it('projection year resolves per scenario and exposes both scenarios for comparison', () => {
    const a = r(2050, 'ssp245'), b = r(2050, 'ssp585')
    expect(a.kind).toBe('projection'); expect(b.kind).toBe('projection')
    if (a.kind === 'projection' && b.kind === 'projection') {
      expect(b.stat.mean).toBeGreaterThan(a.stat.mean)          // selector changes the data
      expect(Object.keys(a.byScenario).sort()).toEqual(['ssp245', 'ssp585'])
      expect(a.window.start_year).toBe(2040)
    }
  })
  it('2100 window reports clipping', () => { const x = r(2100); expect(x.kind === 'projection' && x.window.clipped).toBe(true) })
  it('missing datasets yield unavailable, not fabricated values', () => {
    expect(r(2010, 'ssp245', null, null).kind).toBe('unavailable')
    expect(r(2050, 'ssp245', o, null).kind).toBe('unavailable')
    expect(r(2025, 'ssp245', null, p).kind).toBe('unavailable')
  })
  it('metricValue: null when unavailable; absolute vs anomaly otherwise', () => {
    expect(metricValue(r(2028), 'absolute')).toBeNull()
    expect(metricValue(r(2010), 'absolute')).toBeCloseTo(21); expect(metricValue(r(2010), 'anomaly')).toBeCloseTo(0.5)
    expect(metricValue(r(2050), 'anomaly')).toBeCloseTo(1)
  })
  it('available years and mode', () => {
    expect(allAvailableYears(o, p)).not.toContain(2000); expect(allAvailableYears(o, p)).toContain(2075)
    expect(modeForYear(2010, o, p)).toBe('past'); expect(modeForYear(2025, o, p)).toBe('present'); expect(modeForYear(2050, o, p)).toBe('future')
  })
})

describe('chart rows', () => {
  it('keeps observed and projection in separate fields (never joined)', () => {
    const rows = buildChartRows(o, p, 'absolute')
    expect(rows.find((x) => x.year === 2025)?.ssp245).toBeUndefined()
    expect(rows.find((x) => x.year === 2050)?.obs).toBeUndefined()
    expect(rows.find((x) => x.year === 2000)?.obs).toBeUndefined() // incomplete year not plotted
  })
  it('anomaly mode subtracts the product baseline for observations', () => {
    const rows = buildChartRows(o, p, 'anomaly')
    expect(rows.find((x) => x.year === 2010)?.obs).toBeCloseTo(0.5)
    expect(rows.find((x) => x.year === 2050)?.ssp245).toBeCloseTo(1)
  })
  it('error bars encode min–max spread', () => {
    const row = buildChartRows(o, p, 'absolute').find((x) => x.year === 2050)!
    const mean = row.ssp245 as number
    expect(row.ssp245_err).toEqual([mean - 21, 25 - mean])
  })
})
