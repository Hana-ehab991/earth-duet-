import { create } from 'zustand'

export interface Settings {
  /** 'system' follows prefers-reduced-motion */
  motion: 'system' | 'reduce' | 'full'
  colorBlindPalette: boolean
  highContrast: boolean
  disableColorEffects: boolean
  audioEnabled: boolean
  volume: number
  muted: boolean
}
const KEY = 'earth-duet.settings.v1'
const defaults: Settings = { motion: 'system', colorBlindPalette: false, highContrast: false, disableColorEffects: false, audioEnabled: false, volume: 0.5, muted: false }

function load(): Settings {
  try {
    const raw = localStorage.getItem(KEY)
    // audioEnabled is never restored: audio must always start from a fresh user gesture.
    return raw ? { ...defaults, ...JSON.parse(raw), audioEnabled: false } : defaults
  } catch { return defaults }
}
function save(s: Settings) { try { localStorage.setItem(KEY, JSON.stringify(s)) } catch { /* storage unavailable */ } }

interface Store extends Settings { set: (p: Partial<Settings>) => void }
export const useSettings = create<Store>((set, get) => ({
  ...load(),
  set: (p) => { set(p); const { set: _s, ...rest } = get(); void _s; save(rest) },
}))

export function prefersReducedMotion(): boolean {
  return typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
}
export function useReducedMotion(): boolean {
  const motion = useSettings((s) => s.motion)
  return motion === 'reduce' || (motion === 'system' && prefersReducedMotion())
}
