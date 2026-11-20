export const pct = (v: number | null | undefined, dp = 0) => (v == null ? '–' : `${(v * 100).toFixed(dp)}%`)
export const num = (v: number | null | undefined, dp = 0) => (v == null ? '–' : v.toLocaleString('en-US', { maximumFractionDigits: dp, minimumFractionDigits: dp }))
export const sat = (v: number | null | undefined) => (v == null ? '–' : v.toFixed(1))

export function dur(s: number | null | undefined) {
  if (s == null) return '–'
  const m = Math.floor(s / 60), r = Math.round(s % 60)
  return m ? `${m}:${String(r).padStart(2, '0')}` : `0:${String(r).padStart(2, '0')}`
}

export function when(iso: string | null | undefined, withTime = true) {
  if (!iso) return '–'
  const d = new Date(iso)
  const today = new Date(), y = new Date(Date.now() - 864e5)
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString()
  const t = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  if (same(d, today)) return withTime ? `Today ${t}` : 'Today'
  if (same(d, y)) return withTime ? `Yesterday ${t}` : 'Yesterday'
  const day = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  return withTime ? `${day}, ${t}` : day
}

export const delta = (now: number | null | undefined, prev: number | null | undefined) =>
  now == null || prev == null ? null : now - prev

export const isArabic = (s: string) => /[؀-ۿ]/.test(s || '')
export const title = (s: string) => (s || '').replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())
