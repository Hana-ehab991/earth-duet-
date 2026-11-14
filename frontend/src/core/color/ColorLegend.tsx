import { gradientCss, legendTicks, type ColorScale } from './scales'

/** Accessible legend with real values. `marker` is the current value's position (0..1) or null when unavailable. */
export default function ColorLegend({ scale, unit, marker, valueLabel, compact }: { scale: ColorScale; unit: string; marker: number | null; valueLabel?: string; compact?: boolean }) {
  const ticks = legendTicks(scale, 5)
  return (
    <figure className="m-0" aria-label={`Color legend: ${scale.label}, fixed range ${scale.domain.min} to ${scale.domain.max} ${unit}`}>
      <div className="relative">
        <div className={`${compact ? 'h-2.5' : 'h-3.5'} w-full rounded-sm ring-1 ring-white/20`} style={{ background: gradientCss(scale) }} />
        {marker !== null && (
          <div className="absolute -top-1 -bottom-1 w-0.5 bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.8)]" style={{ left: `${marker * 100}%` }} aria-hidden>
            <span className="absolute -top-4 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-white px-1 text-[10px] font-semibold text-slate-900">{valueLabel}</span>
          </div>
        )}
      </div>
      <div className="mt-1 flex justify-between text-[10px] tabular-nums text-slate-300">
        {ticks.map((t) => <span key={t.value}>{Number.isInteger(t.value) ? t.value : t.value.toFixed(1)}</span>)}
      </div>
      <figcaption className="mt-0.5 text-[10px] text-slate-400">{unit} · fixed scale (not rescaled per year) · {scale.label}</figcaption>
    </figure>
  )
}
