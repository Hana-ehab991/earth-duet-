import { Play, Volume2, VolumeX, Square } from 'lucide-react'
import { useSettings } from '../settings/settingsStore'

export interface AudioControlsProps {
  enabled: boolean
  busy: boolean
  error: string | null
  onEnable: () => void
  onDisable: () => void
  onCalibrate: () => void
  onStop: () => void
  calibrating: boolean
  /** Always-visible text equivalent of what is currently audible. */
  textAlternative: string
  calibrationLabel?: string
}

export default function AudioControls(p: AudioControlsProps) {
  const { volume, muted, set } = useSettings()
  const btn = 'inline-flex items-center gap-1.5 rounded-md border border-cyan-400/40 px-2.5 py-1.5 text-xs font-medium text-cyan-100 hover:bg-cyan-400/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300 disabled:opacity-50'
  return (
    <div className="space-y-2.5 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        {!p.enabled ? (
          <button className={btn} onClick={p.onEnable} disabled={p.busy} aria-describedby="audio-help">
            <Volume2 size={14} aria-hidden /> {p.busy ? 'Starting audio…' : 'Enable sound'}
          </button>
        ) : (
          <>
            <button className={btn} onClick={p.onDisable}><VolumeX size={14} aria-hidden /> Disable sound</button>
            <button className={btn} aria-pressed={muted} onClick={() => set({ muted: !muted })}>{muted ? 'Unmute' : 'Mute'}</button>
          </>
        )}
        {p.enabled && (p.calibrating
          ? <button className={btn} onClick={p.onStop}><Square size={14} aria-hidden /> Stop</button>
          : <button className={btn} onClick={p.onCalibrate}><Play size={14} aria-hidden /> Calibration example</button>)}
      </div>
      <p id="audio-help" className="text-slate-400">Sound starts only after you press “Enable sound”. It is off by default.</p>
      <label className="flex items-center gap-3 text-slate-300">
        <span className="w-14">Volume</span>
        <input type="range" min={0} max={100} step={1} value={Math.round(volume * 100)} onChange={(e) => set({ volume: Number(e.target.value) / 100 })}
          aria-valuetext={`${Math.round(volume * 100)} percent${muted ? ', muted' : ''}`} className="flex-1 accent-cyan-400" />
        <span className="w-9 text-right tabular-nums">{Math.round(volume * 100)}%</span>
      </label>
      {p.calibrationLabel && <p role="status" className="rounded bg-cyan-400/10 px-2 py-1 text-cyan-100">{p.calibrationLabel}</p>}
      {p.error && <p role="alert" className="text-red-300">{p.error}</p>}
      <p className="rounded border border-slate-600/30 bg-slate-900/50 p-2 text-slate-300"><span className="font-semibold text-slate-200">Text equivalent: </span>{p.textAlternative}</p>
    </div>
  )
}
