import type { FeatureDefinition } from './featureRegistry'

export default function PlannedFeature({ feature, reuses }: { feature: Pick<FeatureDefinition, 'label' | 'description'>; reuses: string[] }) {
  return (
    <div className="grid flex-1 place-items-center overflow-y-auto p-6">
      <div className="max-w-xl rounded-2xl border border-cyan-400/20 bg-[#0b1530]/80 p-6 text-sm text-slate-200">
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-widest text-amber-300">Planned · not implemented yet</p>
        <h1 className="mb-2 text-2xl font-semibold text-white">{feature.label}</h1>
        <p className="mb-4 text-slate-300">{feature.description}</p>
        <p className="mb-1 text-xs font-semibold text-cyan-200">Will plug into existing shared infrastructure:</p>
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-slate-300">{reuses.map((r) => <li key={r}>{r}</li>)}</ul>
        <p className="mt-4 text-xs text-slate-400">See docs/ARCHITECTURE.md → “Adding a feature”.</p>
      </div>
    </div>
  )
}
