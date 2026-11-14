import { Suspense, useEffect, useState } from 'react'
import { features } from './featureRegistry'
import { useSettings } from '../core/settings/settingsStore'

const idFromHash = () => features.find((f) => `#/${f.id}` === window.location.hash)?.id ?? features[0].id

export default function App() {
  const [active, setActive] = useState(idFromHash)
  const hc = useSettings((s) => s.highContrast)
  useEffect(() => { const h = () => setActive(idFromHash()); window.addEventListener('hashchange', h); return () => window.removeEventListener('hashchange', h) }, [])
  useEffect(() => { document.documentElement.dataset.contrast = hc ? 'high' : 'normal' }, [hc])
  const feature = features.find((f) => f.id === active) ?? features[0]
  const Page = feature.page
  return (
    <div className="flex h-dvh flex-col bg-[#050b1d] text-slate-100">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-cyan-300 focus:px-3 focus:py-2 focus:text-slate-900">Skip to content</a>
      <header className="flex items-center gap-3 overflow-x-auto border-b border-cyan-400/20 bg-[#08112a] px-4 py-2">
        <div className="flex shrink-0 items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-cyan-400/20 ring-1 ring-cyan-300/60" aria-hidden><span className="h-3.5 w-3.5 rounded-full bg-cyan-300" /></span>
          <div className="leading-tight"><div className="text-sm font-semibold tracking-wide text-white">Earth Duet</div><div className="hidden text-[10px] uppercase tracking-[0.18em] text-cyan-300/80 sm:block">The Earth Information Jukebox</div></div>
        </div>
        <nav aria-label="Features" className="ml-1 flex shrink-0 gap-1">
          {features.map((f) => (
            <a key={f.id} href={`#/${f.id}`} aria-current={f.id === active ? 'page' : undefined}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium focus-visible:outline-2 focus-visible:outline-cyan-300 ${f.id === active ? 'bg-cyan-400/20 text-white ring-1 ring-cyan-300/60' : 'text-slate-300 hover:bg-slate-700/40'}`}>
              <f.icon size={14} aria-hidden />{f.label}{f.status === 'planned' && <span className="rounded bg-slate-700 px-1 text-[9px] uppercase text-slate-300">soon</span>}
            </a>
          ))}
        </nav>
      </header>
      <div id="main-content" className="flex min-h-0 flex-1 flex-col">
        <Suspense fallback={<div className="grid flex-1 place-items-center text-sm text-slate-400">Loading…</div>}><Page key={feature.id} /></Suspense>
      </div>
    </div>
  )
}
