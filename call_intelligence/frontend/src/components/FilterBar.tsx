import { X } from 'lucide-react'
import { PERIODS, type Filters } from '@/lib/filters'
import { RESOLUTION, MOODS } from './labels'
import { useEnt } from './Shell'

/** Period + the common call filters. Values live in the URL (useFilters). */
export function FilterBar({ f, set, clear, extra, show = ['period', 'resolution', 'reason', 'agent', 'sat', 'mood'] }: {
  f: Filters; set: (p: Filters) => void; clear: () => void; extra?: React.ReactNode; show?: string[]
}) {
  const { meta, ent } = useEnt()
  const cats = (meta?.categories || []).filter((c: any) => c.active)
  const agents = meta?.agents || []
  const active = Object.entries(f).filter(([k, v]) => k !== 'period' && v)
  const catName = (code: string) => cats.find((c: any) => c.code === code)?.name || code
  const agentName = (id: string) => agents.find((a: any) => a.id === id)?.name || 'agent'
  const label = (k: string, v: string) => ({
    resolution: v.split(',').map(x => RESOLUTION[x]?.label || x).join(', '), reason: v.split(',').map(catName).join(', '),
    agent: agentName(v), sat_max: `Satisfaction ≤ ${v}`, sat_min: `Satisfaction ≥ ${v}`, mood_end: `Ended ${v.replace(/,/g, ' or ')}`,
    review: 'Needs review', compliance: 'Compliance issue', repeat: 'Repeat calls', churn: `Churn risk: ${v}`, q: `“${v}”`,
    customer: 'One customer', risk: `Risk: ${v}`, status: `Status: ${v.replace(/,/g, ', ')}`, sentiment: v, team: 'Team',
    date_from: `From ${v}`, date_to: `To ${v}`,
  } as Record<string, string>)[k] || `${k}: ${v}`
  return (
    <div className="filters">
      {show.includes('period') && <div className="tabs" role="tablist">{PERIODS.map(([v, l]) =>
        <button key={v} className={(f.period || '30d') === v ? 'on' : ''} onClick={() => set({ period: v })}>{l}</button>)}</div>}
      {show.includes('resolution') && <select className="input" style={{ width: 160 }} value={f.resolution || ''} onChange={e => set({ resolution: e.target.value })} aria-label="Resolution">
        <option value="">Any outcome</option>{Object.entries(RESOLUTION).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}</select>}
      {show.includes('reason') && <select className="input" style={{ width: 210 }} value={f.reason || ''} onChange={e => set({ reason: e.target.value })} aria-label="Reason">
        <option value="">Any reason</option>{cats.map((c: any) => <option key={c.enterprise + c.code} value={c.code}>{ent === 'all' ? `${c.enterprise.toUpperCase()} · ` : ''}{c.name}</option>)}</select>}
      {show.includes('agent') && <select className="input" style={{ width: 170 }} value={f.agent || ''} onChange={e => set({ agent: e.target.value })} aria-label="Agent">
        <option value="">Any agent</option>{agents.map((a: any) => <option key={a.id} value={a.id}>{a.name}{ent === 'all' ? ` (${a.enterprise.toUpperCase()})` : ''}</option>)}</select>}
      {show.includes('sat') && <select className="input" style={{ width: 160 }} value={f.sat_max || ''} onChange={e => set({ sat_max: e.target.value })} aria-label="Satisfaction">
        <option value="">Any satisfaction</option><option value="2">Unhappy (1–2)</option><option value="3">3 or less</option></select>}
      {show.includes('mood') && <select className="input" style={{ width: 160 }} value={f.mood_end || ''} onChange={e => set({ mood_end: e.target.value })} aria-label="Mood at the end">
        <option value="">Any mood at the end</option>{Object.entries(MOODS).map(([k, m]) => <option key={k} value={k}>Ended {m.label.toLowerCase()}</option>)}
        <option value="angry,frustrated">Ended angry or frustrated</option></select>}
      {extra}
      {active.map(([k, v]) => <span key={k} className="chip on">{label(k, v!)}<X size={13} className="x" onClick={() => set({ [k]: '' })} /></span>)}
      {active.length > 0 && <button className="btn sm ghost" onClick={clear}>Clear</button>}
    </div>
  )
}
