import type * as ToneNS from 'tone'

type ToneModule = typeof ToneNS

/** A thing that can make sound from data. Registered with the engine so all are disposed together. */
export interface Sonifier {
  dispose(): void
}

/**
 * Shared audio infrastructure. Tone.js is imported lazily and the AudioContext only starts inside
 * a user gesture (start() must be called from a click/keypress handler).
 * Signal chain: sonifier → master gain (volume, ramped) → limiter → destination.
 */
export class AudioEngine {
  private tone: ToneModule | null = null
  private master: ToneNS.Gain | null = null
  private limiter: ToneNS.Limiter | null = null
  private sonifiers = new Set<Sonifier>()
  private _volume = 0.5
  private _muted = false
  private starting: Promise<void> | null = null

  get ready() { return this.tone !== null && this.master !== null }
  get Tone(): ToneModule { if (!this.tone) throw new Error('AudioEngine not started'); return this.tone }
  get input(): ToneNS.Gain { if (!this.master) throw new Error('AudioEngine not started'); return this.master }

  /** Must be called from a user gesture. Idempotent. */
  start(): Promise<void> {
    if (this.ready) return Promise.resolve()
    this.starting ??= (async () => {
      const Tone = await import('tone')
      await Tone.start()
      this.limiter = new Tone.Limiter(-6).toDestination()
      this.master = new Tone.Gain(0).connect(this.limiter)
      this.tone = Tone
      this.applyVolume()
    })().catch((e) => { this.starting = null; throw e })
    return this.starting
  }

  /** Perceptual-ish taper: gain = 0.6 · v² (max 0.6), ramped to avoid clicks. */
  private applyVolume() {
    if (!this.master) return
    const g = this._muted ? 0 : 0.6 * this._volume * this._volume
    this.master.gain.rampTo(g, 0.08)
  }
  setVolume(v: number) { this._volume = Math.min(1, Math.max(0, v)); this.applyVolume() }
  setMuted(m: boolean) { this._muted = m; this.applyVolume() }

  register<T extends Sonifier>(s: T): T { this.sonifiers.add(s); return s }
  unregister(s: Sonifier) { this.sonifiers.delete(s); s.dispose() }

  dispose() {
    this.sonifiers.forEach((s) => s.dispose())
    this.sonifiers.clear()
    this.master?.dispose(); this.limiter?.dispose()
    this.master = null; this.limiter = null; this.tone = null; this.starting = null
  }
}

export const audioEngine = new AudioEngine()
