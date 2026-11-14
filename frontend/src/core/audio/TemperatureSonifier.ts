import type * as ToneNS from 'tone'
import type { AudioEngine, Sonifier } from './AudioEngine'
import type { SoundMappingConfig } from './SoundMappingConfig'
import { valueToFilterHz, valueToFrequency } from './mapping'

/**
 * Continuous-value sonifier (pitch + brightness). Despite the name it is variable-agnostic:
 * the SoundMappingConfig decides range/unit/pitch span, so other features can reuse it.
 * All changes are ramped; nothing ever jumps in level or frequency.
 */
export class TemperatureSonifier implements Sonifier {
  private osc: ToneNS.Oscillator
  private filter: ToneNS.Filter
  private env: ToneNS.Gain
  private fadeTimer: ReturnType<typeof setTimeout> | null = null
  private seqTimers: ReturnType<typeof setTimeout>[] = []
  private sustain = false
  private sequencing = false
  private disposed = false

  constructor(private engine: AudioEngine, private cfg: SoundMappingConfig) {
    const T = engine.Tone
    this.env = new T.Gain(0).connect(engine.input)
    this.filter = new T.Filter({ type: 'lowpass', frequency: cfg.filterMin, Q: 0.7 }).connect(this.env)
    this.osc = new T.Oscillator({ type: cfg.waveform, frequency: cfg.baseFrequency }).connect(this.filter)
    this.osc.start()
  }

  setConfig(cfg: SoundMappingConfig) { this.cfg = cfg }
  /** While true (timeline playing) the tone is held; otherwise it fades after a short "ping". */
  setSustain(b: boolean) { this.sustain = b; if (!b) this.scheduleFade(600) }

  /** value === null means "no verified data": fade to silence rather than inventing a pitch. */
  update(value: number | null) {
    if (this.disposed || this.sequencing) return
    if (value === null) { this.fadeOut(0.25); return }
    this.setPitch(value)
    this.env.gain.cancelScheduledValues(this.engine.Tone.now())
    this.env.gain.rampTo(this.cfg.peakGain, 0.15)
    if (!this.sustain) this.scheduleFade(1400)
  }

  private setPitch(value: number) {
    this.osc.frequency.rampTo(valueToFrequency(value, this.cfg), this.cfg.glideSeconds)
    this.filter.frequency.rampTo(valueToFilterHz(value, this.cfg), this.cfg.glideSeconds)
  }
  private scheduleFade(ms: number) {
    if (this.fadeTimer) clearTimeout(this.fadeTimer)
    this.fadeTimer = setTimeout(() => this.fadeOut(0.6), ms)
  }
  private fadeOut(sec: number) { if (!this.disposed) this.env.gain.rampTo(0, sec) }

  /** Play values one after another (calibration, scenario comparison). onStep reports progress for on-screen text. */
  playSequence(values: number[], stepMs = 1100, onStep?: (i: number) => void): Promise<void> {
    this.stopSequence()
    this.sequencing = true
    return new Promise((resolve) => {
      values.forEach((v, i) => {
        this.seqTimers.push(setTimeout(() => {
          if (this.disposed) return
          onStep?.(i); this.setPitch(v)
          this.env.gain.rampTo(this.cfg.peakGain, 0.12)
        }, i * stepMs))
      })
      this.seqTimers.push(setTimeout(() => this.fadeOut(0.3), values.length * stepMs - 150))
      this.seqTimers.push(setTimeout(() => { this.sequencing = false; resolve() }, values.length * stepMs + 350))
    })
  }
  stopSequence() {
    this.seqTimers.forEach(clearTimeout); this.seqTimers = []
    if (this.sequencing) { this.sequencing = false; this.fadeOut(0.15) }
  }

  dispose() {
    if (this.disposed) return
    this.disposed = true
    if (this.fadeTimer) clearTimeout(this.fadeTimer)
    this.seqTimers.forEach(clearTimeout)
    this.osc.stop(); this.osc.dispose(); this.filter.dispose(); this.env.dispose()
  }
}
