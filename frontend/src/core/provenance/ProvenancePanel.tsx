import { Fragment } from 'react'
import type { Baseline, Geometry, Processing, RecordType, Source } from '../api/types'
import { Badge } from '../ui/Panel'

export interface ProvenanceInfo {
  title: string
  recordType: RecordType
  unit: string
  source: Source
  geometry: Geometry
  processing: Processing
  baseline: Baseline
  extra?: { label: string; value: string }[]
}

export const RECORD_TYPE_LABEL: Record<RecordType, string> = {
  observation: 'Observation', reanalysis: 'Reanalysis (model-assisted)', model_historical: 'Model historical simulation',
  projection: 'Climate projection (conditional)', synthetic_demo: 'SYNTHETIC DEMO — not real data',
}

/** Generic provenance card — any dataset that follows the shared schema renders here. */
export default function ProvenancePanel({ items }: { items: ProvenanceInfo[] }) {
  return (
    <div className="space-y-2">
      {items.map((p) => (
        <details key={p.title} className="group rounded-lg border border-slate-600/30 bg-slate-900/40 p-2.5 text-xs open:bg-slate-900/70">
          <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 font-medium text-slate-100">
            {p.title}
            <Badge tone={p.recordType === 'synthetic_demo' ? 'red' : p.recordType === 'projection' ? 'orange' : 'cyan'}>{RECORD_TYPE_LABEL[p.recordType]}</Badge>
          </summary>
          <dl className="mt-2 grid grid-cols-[6.5rem_1fr] gap-x-2 gap-y-1 text-slate-300">
            <dt className="text-slate-400">Source</dt><dd><a className="underline decoration-dotted" href={p.source.url} target="_blank" rel="noreferrer">{p.source.name}</a></dd>
            <dt className="text-slate-400">Parameter</dt><dd>{p.source.parameter} <span className="text-slate-400">({p.unit})</span></dd>
            <dt className="text-slate-400">Product</dt><dd>{p.source.product}</dd>
            <dt className="text-slate-400">Geometry</dt><dd>{p.geometry.type}{p.geometry.latitude != null && ` @ ${p.geometry.latitude}°, ${p.geometry.longitude}°`}. {p.geometry.spatial_support}</dd>
            <dt className="text-slate-400">Processing</dt><dd>{p.processing.method}</dd>
            {p.processing.missing_value_handling && (<><dt className="text-slate-400">Missing data</dt><dd>{p.processing.missing_value_handling}</dd></>)}
            <dt className="text-slate-400">Baseline</dt><dd>{p.baseline.description} ({p.baseline.period[0]}–{p.baseline.period[1]}{p.baseline.mean != null ? `, mean ${p.baseline.mean.toFixed(2)} ${p.unit}` : ''})</dd>
            {p.extra?.map((e) => (<Fragment key={e.label}><dt className="text-slate-400">{e.label}</dt><dd>{e.value}</dd></Fragment>))}
            {p.processing.retrieved_at && (<><dt className="text-slate-400">Retrieved</dt><dd>{p.processing.retrieved_at}</dd></>)}
            {p.source.citation_note && (<><dt className="text-slate-400">Note</dt><dd>{p.source.citation_note}</dd></>)}
          </dl>
        </details>
      ))}
    </div>
  )
}
