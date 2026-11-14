/** SYNTHETIC TEST FIXTURES — used only to test logic. Not scientific data. */
import type { ObservedDataset, ProjectionDataset } from '../../frontend/src/core/api/types'

const src = { name: 'test', url: 'about:blank', product: 'test', parameter: 'T2M' }
const geo = { type: 'point' as const, latitude: 30, longitude: 31, support_bbox: [31, 30, 31.25, 30.25], spatial_support: 'test' }
const proc = { method: 'test' }

export function makeObserved(): ObservedDataset {
  const records = []
  for (let y = 1990; y <= 2025; y++) records.push({ year: y, value: y === 2000 ? null : 20 + (y - 1990) * 0.05, complete: y !== 2000, n_months: y === 2000 ? 11 : 12, reason: y === 2000 ? 'Only 11/12 months' : null })
  return { dataset_id: 't', location_id: 'cairo', variable_id: 'air_temperature', record_type: 'reanalysis', is_demo: false, unit: '°C', source: src, geometry: geo, processing: proc,
    baseline: { period: [1995, 2014], mean: 20.5, description: 'b' }, coverage: {}, records }
}
export function makeProjection(): ProjectionDataset {
  const ens = [] as ProjectionDataset['ensemble']
  for (const scenario of ['ssp245', 'ssp585']) for (const t of [2030, 2050, 2075, 2100]) {
    const k = scenario === 'ssp585' ? 2 : 1
    ens.push({ scenario, target_year: t, n_models: 2, mean: 22 + k * (t - 2000) / 50, min: 21, max: 25, std: 1, anomaly_mean: k * (t - 2000) / 50, anomaly_min: 0.5, anomaly_max: 3 })
  }
  return { dataset_id: 'p', location_id: 'cairo', variable_id: 'air_temperature', record_type: 'projection', is_demo: false, unit: '°C', source: src, geometry: geo, processing: proc,
    baseline: { period: [1995, 2014], mean: 21, description: 'b' }, models: [{ id: 'M1' }, { id: 'M2' }], scenarios: ['ssp245', 'ssp585'],
    windows: [2030, 2050, 2075, 2100].map((t) => ({ target_year: t, start_year: t - 10, end_year: Math.min(2100, t + 9), clipped: t === 2100 })),
    records: [{ scenario: 'ssp245', target_year: 2050, model: 'M1', value: 23, baseline: 21, anomaly: 2 }], ensemble: ens, uncertainty_note: 'n' }
}
