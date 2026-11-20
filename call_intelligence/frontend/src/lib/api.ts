// API client. The token lives in localStorage (and an httpOnly cookie for audio and downloads).
const KEY = 'ci-token'

export const token = {
  get: () => { try { return localStorage.getItem(KEY) || '' } catch { return '' } },
  set: (t: string) => { try { localStorage.setItem(KEY, t) } catch { /* private mode */ } },
  clear: () => { try { localStorage.removeItem(KEY) } catch { /* private mode */ } },
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) }
  const t = token.get()
  if (t) headers.Authorization = `Bearer ${t}`
  let body = opts.body
  if (opts.json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.json) }
  const res = await fetch(`/api${path}`, { ...opts, headers, body, credentials: 'same-origin' })
  if (res.status === 401 && !path.startsWith('/auth')) {
    token.clear()
    if (!location.pathname.startsWith('/login')) location.assign('/login?next=' + encodeURIComponent(location.pathname + location.search))
  }
  if (!res.ok) {
    let msg = res.statusText
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not json */ }
    throw new ApiError(res.status, msg)
  }
  const ct = res.headers.get('content-type') || ''
  return (ct.includes('application/json') ? res.json() : res.text()) as Promise<T>
}

export function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

/** Server-sent events over POST (the assistant streams its steps and answer). */
export async function stream(path: string, json: unknown, onEvent: (e: any) => void, signal?: AbortSignal) {
  const res = await fetch(`/api${path}`, {
    method: 'POST', signal, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token.get()}` }, body: JSON.stringify(json),
  })
  if (!res.ok || !res.body) throw new ApiError(res.status, 'The assistant is not available.')
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i)
      buf = buf.slice(i + 2)
      const line = chunk.split('\n').find(l => l.startsWith('data: '))
      if (line) { try { onEvent(JSON.parse(line.slice(6))) } catch { /* partial */ } }
    }
  }
}

export async function download(path: string, filename: string) {
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${token.get()}` } })
  if (!res.ok) throw new ApiError(res.status, 'Download failed')
  const url = URL.createObjectURL(await res.blob())
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
