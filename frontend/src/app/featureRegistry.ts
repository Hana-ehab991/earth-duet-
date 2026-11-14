import { lazy, type ComponentType, type LazyExoticComponent } from 'react'
import { AudioLines, Hourglass, Palette } from 'lucide-react'

/**
 * Feature registry — the single place to add a new Earth Duet feature.
 * A feature = { id, label, status, page }. It may use any shared infrastructure in src/core
 * (globe, API client, timeline factory, color engine, audio engine, provenance) but owns its own state under src/features/<id>.
 */
export interface FeatureDefinition {
  id: string
  label: string
  description: string
  status: 'available' | 'planned'
  icon: ComponentType<{ size?: number; 'aria-hidden'?: boolean }>
  page: LazyExoticComponent<ComponentType>
}

export const features: FeatureDefinition[] = [
  { id: 'time-travel', label: 'Time Travel', status: 'available', icon: Hourglass,
    description: 'Explore past observations, the latest year, and conditional future climate projections on a 3D globe.',
    page: lazy(() => import('../features/timeTravel/TimeTravelPage')) },
  { id: 'earth-duet', label: 'Earth Duet', status: 'available', icon: AudioLines,
    description: 'Compare two regions with the same variable, aligned time and shared sound scale, then take a listening challenge.',
    page: lazy(() => import('../features/earthDuet/EarthDuetPage')) },
  { id: 'color-symphony', label: 'Color Symphony', status: 'available', icon: Palette,
    description: 'Hear and see every year of real NASA POWER temperature as a color and a note, with an interactive legend and timeline.',
    page: lazy(() => import('../features/colorSymphony/ColorSymphonyPage')) },
]
