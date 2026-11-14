const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiRequestError extends Error {
  constructor(public status: number, public code: string, message: string, public hint?: string | null) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

export type Params = Record<string, string | number | undefined | null>

export function buildUrl(path: string, params: Params = {}): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  const qs = q.toString()
  return `${BASE}${path}${qs ? `?${qs}` : ''}`
}

/** GET JSON with abort support. Structured backend errors become ApiRequestError. */
export async function apiGet<T>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(buildUrl(path, params), { signal, headers: { Accept: 'application/json' } })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiRequestError(0, 'network_error', 'Could not reach the Earth Duet API.', 'Is the backend running on port 8000?')
  }
  if (!res.ok) {
    let body: { error?: { code?: string; message?: string; hint?: string } } = {}
    try { body = await res.json() } catch { /* non-JSON error */ }
    throw new ApiRequestError(res.status, body.error?.code ?? 'http_error', body.error?.message ?? `HTTP ${res.status}`, body.error?.hint)
  }
  return (await res.json()) as T
}

/** POST JSON with abort support. Same structured-error handling as apiGet. */
export async function apiPost<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(buildUrl(path), { method: 'POST', signal, headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiRequestError(0, 'network_error', 'Could not reach the Earth Duet API.', 'Is the backend running on port 8000?')
  }
  if (!res.ok) {
    let b: { error?: { code?: string; message?: string; hint?: string } } = {}
    try { b = await res.json() } catch { /* non-JSON error */ }
    throw new ApiRequestError(res.status, b.error?.code ?? 'http_error', b.error?.message ?? `HTTP ${res.status}`, b.error?.hint)
  }
  try {
    return (await res.json()) as T
  } catch {
    throw new ApiRequestError(res.status, 'invalid_response', 'The API answered with something that is not valid JSON.')
  }
}
