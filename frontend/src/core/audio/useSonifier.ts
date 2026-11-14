import { useCallback, useEffect, useRef, useState } from 'react'
import { audioEngine } from './AudioEngine'
import { TemperatureSonifier } from './TemperatureSonifier'
import type { SoundMappingConfig } from './SoundMappingConfig'
import { useSettings } from '../settings/settingsStore'

/**
 * React binding for the shared AudioEngine. enable() MUST be called from a user gesture.
 * Any feature can use it with its own SoundMappingConfig.
 */
export function useSonifier(cfg: SoundMappingConfig) {
  const { audioEnabled, volume, muted, set } = useSettings()
  const son = useRef<TemperatureSonifier | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [sequenceStep, setSequenceStep] = useState<number | null>(null)

  const enable = useCallback(async () => {
    setBusy(true); setError(null)
    try {
      await audioEngine.start()
      son.current ??= audioEngine.register(new TemperatureSonifier(audioEngine, cfg))
      set({ audioEnabled: true })
    } catch (e) {
      setError(`Audio could not start: ${(e as Error).message}`)
    } finally { setBusy(false) }
  }, [cfg, set])

  const disable = useCallback(() => {
    if (son.current) { audioEngine.unregister(son.current); son.current = null }
    set({ audioEnabled: false }); setSequenceStep(null)
  }, [set])

  useEffect(() => { if (audioEngine.ready) { audioEngine.setVolume(volume); audioEngine.setMuted(muted) } }, [volume, muted, audioEnabled])
  useEffect(() => { son.current?.setConfig(cfg) }, [cfg])
  useEffect(() => () => { if (son.current) { audioEngine.unregister(son.current); son.current = null } }, [])

  const update = useCallback((value: number | null) => { if (audioEnabled) son.current?.update(value) }, [audioEnabled])
  const setSustain = useCallback((b: boolean) => son.current?.setSustain(b), [])
  const playSequence = useCallback(async (values: number[]) => {
    if (!son.current) return
    await son.current.playSequence(values, 1100, setSequenceStep)
    setSequenceStep(null)
  }, [])
  const stop = useCallback(() => { son.current?.stopSequence(); setSequenceStep(null) }, [])

  return { enabled: audioEnabled, enable, disable, update, setSustain, playSequence, stop, error, busy, sequenceStep }
}
