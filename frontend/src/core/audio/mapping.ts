import type { SoundMappingConfig } from './SoundMappingConfig'
import { normalize } from './DataNormalizer'

export const valueToFrequency = (value: number, cfg: SoundMappingConfig): number =>
  cfg.baseFrequency * Math.pow(2, normalize(value, cfg.range).n * cfg.octaves)

export const valueToFilterHz = (value: number, cfg: SoundMappingConfig): number =>
  cfg.filterMin * Math.pow(cfg.filterMax / cfg.filterMin, normalize(value, cfg.range).n)

const NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B']
/** Nearest equal-tempered note name for a frequency (A4 = 440 Hz). */
export function frequencyToNoteName(f: number): string {
  const midi = Math.round(69 + 12 * Math.log2(f / 440))
  return `${NAMES[((midi % 12) + 12) % 12]}${Math.floor(midi / 12) - 1}`
}

/** Text alternative to sound — usable by anyone who cannot or does not listen. */
export function describeSound(value: number | null, cfg: SoundMappingConfig): string {
  if (value === null) return 'Silent: no verified data for this year.'
  const f = valueToFrequency(value, cfg)
  const { n, clamped } = normalize(value, cfg.range)
  const extra = clamped ? ` (value is ${clamped} the reference range, so pitch is held at the ${clamped === 'above' ? 'top' : 'bottom'})` : ''
  return `Pitch ${frequencyToNoteName(f)} (${f.toFixed(0)} Hz), ${(n * 100).toFixed(0)}% of the ${cfg.range.min}–${cfg.range.max} ${cfg.unit} reference range${extra}.`
}
