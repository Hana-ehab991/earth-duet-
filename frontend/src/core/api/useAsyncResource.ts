import { useEffect, useState } from 'react'

export type AsyncState<T> =
  | { status: 'idle' | 'loading'; data: T | null; error: null }
  | { status: 'success'; data: T; error: null }
  | { status: 'error'; data: null; error: Error }

/**
 * Runs `fetcher` whenever `deps` change. The previous request is aborted and its result ignored,
 * so rapid changes (e.g. dragging a slider) can never apply stale data (no race conditions).
 * Pass `enabled=false` to stay idle.
 */
export function useAsyncResource<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: unknown[], enabled = true): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: enabled ? 'loading' : 'idle', data: null, error: null })
  useEffect(() => {
    if (!enabled) { setState({ status: 'idle', data: null, error: null }); return }
    const ctl = new AbortController()
    setState((s) => ({ status: 'loading', data: s.status === 'success' ? s.data : null, error: null }) as AsyncState<T>)
    fetcher(ctl.signal).then(
      (data) => { if (!ctl.signal.aborted) setState({ status: 'success', data, error: null }) },
      (error: Error) => { if (!ctl.signal.aborted && error.name !== 'AbortError') setState({ status: 'error', data: null, error }) },
    )
    return () => ctl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled])
  return state
}

/** Debounce a rapidly-changing value (e.g. slider year) before it triggers network work. */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}
