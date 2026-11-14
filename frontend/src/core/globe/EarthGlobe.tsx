import { useEffect, useRef, useState } from 'react'
import { GlobeEngine, type GlobeMarker, type OverlayStatus, type SupportRect, type TileOverlaySpec } from './GlobeEngine'

export interface EarthGlobeProps {
  markers: GlobeMarker[]
  onMarkerClick: (id: string) => void
  /** Optional. When provided, clicks on the globe surface are reported (lat/lon, or null if the click missed the globe). Time Travel does not use it. */
  onGlobeClick?: (c: { lat: number; lon: number } | null) => void
  /** Camera target; flies whenever `key` changes. */
  flyTo: { key: string; lat: number; lon: number; height: number } | null
  tileOverlay: TileOverlaySpec | null
  onOverlayStatus: (s: OverlayStatus) => void
  supportRect: SupportRect | null
  reducedMotion: boolean
  label: string
}

/** Reusable globe view. Any feature can mount it and feed it layers; it holds no feature logic. */
export default function EarthGlobe(p: EarthGlobeProps) {
  const host = useRef<HTMLDivElement>(null)
  const engine = useRef<GlobeEngine | null>(null)
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null)
  const [initError, setInitError] = useState<string | null>(null)
  const cbs = useRef(p)
  cbs.current = p

  useEffect(() => {
    if (!host.current) return
    let g: GlobeEngine
    try {
      g = new GlobeEngine(host.current, import.meta.env.VITE_CESIUM_ION_TOKEN)
    } catch (e) {
      setInitError((e as Error).message || 'WebGL could not be initialised.')
      return
    }
    engine.current = g
    g.onCoordinates = setCoords
    g.onMarkerClick = (id) => cbs.current.onMarkerClick(id)
    g.onGlobeClick = (c) => cbs.current.onGlobeClick?.(c)
    return () => { g.dispose(); engine.current = null }
  }, [])

  const globeClickOn = !!p.onGlobeClick
  useEffect(() => { engine.current?.setGlobeClickEnabled(globeClickOn) }, [globeClickOn])
  useEffect(() => { engine.current?.setMarkers(p.markers) }, [p.markers])
  useEffect(() => {
    if (p.flyTo) engine.current?.flyTo(p.flyTo.lat, p.flyTo.lon, p.flyTo.height, cbs.current.reducedMotion)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.flyTo?.key])
  useEffect(() => { engine.current?.setSupportRect(p.supportRect) }, [p.supportRect?.color, p.supportRect?.label, p.supportRect?.bbox.join(',')])
  useEffect(() => {
    engine.current?.setTileOverlay(p.tileOverlay, (s) => cbs.current.onOverlayStatus(s), !cbs.current.reducedMotion)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.tileOverlay?.id, p.tileOverlay?.url])

  return (
    <div className="relative h-full w-full" role="application" aria-label={p.label}>
      <div ref={host} className="absolute inset-0" />
      {initError && (
        <div className="absolute inset-0 grid place-items-center bg-[#050b1d] p-6 text-center text-sm text-amber-200">
          The 3D globe could not start ({initError}). WebGL is required. All numerical data, charts, color and sound still work.
        </div>
      )}
      <div className="pointer-events-none absolute right-3 top-3 rounded bg-black/55 px-2 py-1 font-mono text-[11px] text-slate-200" aria-live="off">
        {coords ? `${coords.lat.toFixed(3)}°, ${coords.lon.toFixed(3)}°` : 'Pointer outside globe'}
      </div>
    </div>
  )
}
