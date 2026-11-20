import { useSearchParams } from 'react-router-dom'

// Call filters live in the URL, so every view can be shared and reloaded; the same keys as the API.
export const FILTER_KEYS = ['period', 'date_from', 'date_to', 'agent', 'team', 'reason', 'resolution', 'sentiment', 'mood_end',
  'sat_max', 'sat_min', 'churn', 'review', 'compliance', 'repeat', 'customer', 'status', 'q', 'risk'] as const
export type Filters = Partial<Record<(typeof FILTER_KEYS)[number], string>>

export function useFilters(defaults: Filters = { period: '30d' }) {
  const [sp, setSp] = useSearchParams()
  const f: Filters = { ...defaults }
  for (const k of FILTER_KEYS) { const v = sp.get(k); if (v !== null) f[k] = v }
  const set = (patch: Filters, replace = true) => {
    const next = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(patch)) { if (v === undefined || v === '' || v === null) next.delete(k); else next.set(k, String(v)) }
    setSp(next, { replace })
  }
  const clear = () => setSp(new URLSearchParams(defaults.period ? { period: defaults.period } : {}), { replace: true })
  return { f, set, clear, sp }
}

export function toQuery(f: Filters, extra: Record<string, unknown> = {}) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries({ ...f, ...extra })) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const PERIODS: [string, string][] = [['today', 'Today'], ['7d', '7 days'], ['30d', '30 days'], ['90d', '90 days'], ['all', 'All time']]
