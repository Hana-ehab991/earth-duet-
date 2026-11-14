import { describe, expect, it } from 'vitest'
import { createTimelineStore, nextAvailable } from '../../frontend/src/core/timeline/createTimelineStore'
import { buildUrl } from '../../frontend/src/core/api/client'

describe('timeline store', () => {
  const mk = () => { const s = createTimelineStore({ minYear: 1981, maxYear: 2100, year: 2020 }); s.getState().setAvailableYears([2030, 1990, 2025, 2050]); return s }
  it('clamps and rounds years', () => { const s = mk(); s.getState().setYear(3000); expect(s.getState().year).toBe(2100); s.getState().setYear(1900); expect(s.getState().year).toBe(1981) })
  it('steps through available years only', () => {
    const s = mk(); s.getState().setYear(2025); s.getState().stepAvailable(1); expect(s.getState().year).toBe(2030)
    s.getState().stepAvailable(-1); expect(s.getState().year).toBe(2025); s.getState().setYear(1990); s.getState().stepAvailable(-1); expect(s.getState().year).toBe(1990)
  })
  it('playback skips gaps when asked, steps by one year otherwise, and stops at the end', () => {
    const s = mk(); s.getState().setYear(2025); s.getState().tick(); expect(s.getState().year).toBe(2030)
    s.getState().setSkipUnavailable(false); s.getState().tick(); expect(s.getState().year).toBe(2031)
    s.getState().setSkipUnavailable(true); s.getState().setYear(2050); s.getState().play(); s.getState().tick(); expect(s.getState().playing).toBe(false)
  })
  it('instances are independent (reusable by other features)', () => {
    const a = mk(), b = createTimelineStore({ minYear: 2000, maxYear: 2010, year: 2005 }); a.getState().setYear(2040); expect(b.getState().year).toBe(2005)
  })
  it('nextAvailable', () => { expect(nextAvailable([1, 3, 5], 3, 1)).toBe(5); expect(nextAvailable([1, 3, 5], 3, -1)).toBe(1); expect(nextAvailable([1], 1, 1)).toBeNull() })
})
describe('api client', () => { it('builds query strings, skipping empty values', () => { expect(buildUrl('/api/x', { a: 1, b: undefined, c: '', d: 'z' })).toBe('/api/x?a=1&d=z') }) })
