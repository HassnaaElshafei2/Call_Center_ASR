import { Fragment, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlarmWarning, BarChart3, Building2, CalendarClock, CheckCircle2, Clock3, Frown, Headphones, ListTodo, Repeat2,
  Smile, StarFill, Users, Workflow, Tags, ChevronRight, MessageCircle } from '@/components/icons'
import { api } from '@/lib/api'
import { toQuery, useFilters, type Filters } from '@/lib/filters'
import { dur, num, pct, sat } from '@/lib/format'
import { openAsk } from '@/components/Ask'
import { Chart, axis } from '@/components/Chart'
import { cssVar } from '@/lib/theme'
import { FilterBar } from '@/components/FilterBar'
import { MOODS, RESOLUTION } from '@/components/labels'
import { entLogo, Topbar, useEnt, useScreen } from '@/components/Shell'
import { BarList, Empty, Kpi, Modal, Skeleton, Widget } from '@/components/ui'
import emblemWhite from '@/assets/brand/emblem-white.svg'

/** Split the daily trend into up to 8 buckets for the KPI mini bars (calls summed, rates weighted by calls). */
function buckets(trend: any[], key: string, n = 8) {
  const days = trend.filter(d => d.calls)
  if (days.length < 2) return undefined
  const size = Math.ceil(days.length / n)
  const out: number[] = []
  for (let i = 0; i < days.length; i += size) {
    const part = days.slice(i, i + size), calls = part.reduce((a, d) => a + d.calls, 0)
    out.push(key === 'calls' ? calls : part.reduce((a, d) => a + (d[key] ?? 0) * d.calls, 0) / Math.max(1, calls))
  }
  return out
}

export default function Overview() {
  const { ent, base, list } = useEnt()
  const { f, set, clear } = useFilters()
  const nav = useNavigate()
  const [open, setOpen] = useState<string | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['overview', ent, f], queryFn: () => api(`/e/${ent}/overview${toQuery(f)}`) })
  useScreen({ page: 'overview', title: 'Overview dashboard', filters: f, kpis: data?.kpis })
  const calls = (extra: Filters, where = base) => nav(`${where}/calls${toQuery({ ...f, ...extra })}`)
  const k = data?.kpis, p = data?.previous
  const ch = (key: string, pts = true) => {
    if (!k || !p || k[key] == null || p[key] == null) return undefined
    const d = k[key] - p[key]
    return { value: d, label: pts ? `${d > 0 ? '+' : '−'}${Math.abs(d * 100).toFixed(1)}pp` : `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(1)}` }
  }
  const period = { today: 'today', '7d': 'the last 7 days', '30d': 'the last 30 days', '90d': 'the last 90 days', '365d': 'the last year' }[f.period as string] ?? 'this period'
  const act = (a: any) => a.ask ? openAsk(a.ask) : calls(a.filters || {}, a.enterprise && ent === 'all' ? `/e/${a.enterprise}` : base)
  return (
    <>
      <Topbar title="Overview" />
      <div className="content">
        <FilterBar f={f} set={set} clear={clear} />
        {isLoading || !data ? <div className="tray g3" style={{ display: 'grid' }}>{[...Array(6)].map((_, i) => <Skeleton key={i} h={110} />)}</div> : !k.calls ? (
          <Empty icon={Headphones} title="No analysed calls in this period">Upload calls or choose a longer period.</Empty>
        ) : <>
          {!!data.read?.length && <section className="insights" aria-label="Sia AI's read">
            <div className="insights-head"><span className="ai-avatar"><img src={emblemWhite} alt="" /></span>
              <h3><span className="brand-name">Sia AI</span>'s read on {period}</h3><span className="tiny muted">From {num(k.calls)} analysed calls</span></div>
            <div className="insight-grid">{data.read.map((r: any, i: number) => <div key={i} className="insight">
              <span className={`kind ${r.kind === 'positive' ? 'pos' : 'att'}`}>{r.kind === 'positive' ? <StarFill size={14} /> : <AlarmWarning size={14} />}{r.kind === 'positive' ? 'Positive' : 'Attention'}</span>
              <p><b>{r.lead}</b> {r.body}</p>
              <button className={`btn sm ${r.action.primary ? 'primary' : ''}`} onClick={() => act(r.action)}>{r.action.label}</button>
            </div>)}</div>
          </section>}

          <div className="tray g3">
            <Kpi icon={Headphones} label="Calls analysed" value={num(k.calls)} mini={buckets(data.trend, 'calls')}
              change={p ? { value: k.calls - p.calls, label: `${k.calls - p.calls >= 0 ? '+' : '−'}${Math.abs(k.calls - p.calls)}` } : undefined} />
            <Kpi icon={CheckCircle2} label="Fully resolved" value={pct(k.resolved)} suffix={`${pct(k.partly_resolved)} partly`} mini={buckets(data.trend, 'resolved')}
              change={ch('resolved')} onClick={() => calls({ resolution: 'resolved' })} />
            <Kpi icon={Smile} label="Predicted satisfaction" value={sat(k.satisfaction)} suffix="/ 5" mini={buckets(data.trend, 'satisfaction')} change={ch('satisfaction', false)} />
            <Kpi icon={Frown} label="Ended unhappy" value={pct(k.negative)} suffix="angry or frustrated" goodWhenUp={false} mini={buckets(data.trend, 'negative')}
              change={ch('negative')} onClick={() => calls({ mood_end: 'angry,frustrated' })} />
            <Kpi icon={Repeat2} label="Repeat calls" value={pct(k.repeat)} suffix="within 14 days" goodWhenUp={false}
              change={ch('repeat')} onClick={() => calls({ repeat: 'true' })} />
            <Kpi icon={Clock3} label="Average call" value={dur(k.avg_duration_s)} suffix={k.qa != null ? `QA score ${k.qa}` : 'min'} />
          </div>

          <div className="tray" style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(300px, 1fr)' }}>
            <Widget icon={BarChart3} title="Calls and resolution" sub="Calls per day, the last 7 days highlighted; the line is the share fully resolved. Click a day." onExpand={() => setOpen('trend')}
              actions={<div className="legend"><span><span className="dot" style={{ background: 'var(--bar)', borderRadius: 2 }} />Calls</span>
                <span><span className="dot" style={{ background: 'var(--bar-hi)', borderRadius: 2 }} />Last 7 days</span>
                <span><span style={{ width: 12, height: 2, background: 'var(--line-overlay)', display: 'inline-block' }} />Fully resolved</span></div>}>
              <Trend data={data.trend} onDay={d => calls({ date_from: d, date_to: d, period: 'custom' })} />
            </Widget>
            <Widget icon={MessageCircle} title="How calls ended" sub="Resolution, from what was said in the call">
              <Ended res={data.resolution} total={k.calls} flow={data.mood_flow} onPick={r => calls({ resolution: r })} />
            </Widget>
          </div>

          <div className="tray g2">
            <Widget icon={Tags} title="Why customers call" sub="Top reasons, split by how they ended. Click a reason." onExpand={() => setOpen('reasons')}>
              <ReasonBars reasons={data.reasons.slice(0, 8)} onPick={code => calls({ reason: code })} />
            </Widget>
            <Widget icon={Workflow} title="Customer mood journey" sub="Mood at the start and at the end of the call" onExpand={() => setOpen('mood')}>
              <MoodJourney flow={data.mood_flow} onPick={(to: string) => calls({ mood_end: to })} />
            </Widget>
          </div>

          <div className="tray">
            <Widget icon={Users} title="Agents" sub="Ranked by resolution, then predicted satisfaction"
              actions={<button className="btn sm ghost" onClick={() => setOpen('agents')}>View all<ChevronRight size={16} /></button>}>
              <AgentTable agents={data.agents.slice(0, 6)} list={list} showEnt={ent === 'all'} onPick={id => nav(`${base}/agents/${id}${toQuery({ period: f.period })}`)} />
            </Widget>
          </div>

          <div className="tray g3">
            <Widget icon={ListTodo} title="Follow-up work" sub="From the Action Center">
              <div className="grid g3">
                <Tile n={data.work.open_actions} label="Open actions" onClick={() => nav(`${base}/actions`)} />
                <Tile n={data.work.promises_due} label="Promises due" onClick={() => nav(`${base}/actions?tab=promises`)} />
                <Tile n={data.work.recovered} label="Recovered" onClick={() => nav(`${base}/actions?tab=done`)} />
              </div>
              <div className="row small"><span className="pill warn">{k.needs_review}</span><span className="muted">calls need a human review</span>
                <button className="btn sm right" onClick={() => nav(`${base}/review`)}>Review</button></div>
              <div className="row small"><span className="pill bad">{k.churn_high}</span><span className="muted">customers at high churn risk</span>
                <button className="btn sm right" onClick={() => nav(`${base}/customers?risk=high`)}>See</button></div>
            </Widget>
            <Widget icon={CalendarClock} title="When calls come in" sub="Calls by weekday and hour, Cairo time" className="span2">
              <Heat grid={data.heatmap} />
            </Widget>
          </div>

          {!!data.enterprises.length && <div className="tray"><Widget icon={Building2} title="Enterprises side by side" sub="Same period, same measures. Click one to open it.">
            <div className="table-wrap"><table className="table"><thead><tr><th>Enterprise</th><th className="num">Calls</th><th className="num">Fully resolved</th><th className="num">Satisfaction</th><th className="num">Ended unhappy</th><th className="num">Repeat</th></tr></thead>
              <tbody>{data.enterprises.map((e: any) => { const l = entLogo(e); return <tr key={e.id} className="click" onClick={() => nav(`/e/${e.id}/overview${toQuery(f)}`)}>
                <td><span className="row" style={{ gap: 8, flexWrap: 'nowrap' }}><span className="org" style={{ background: l.bg }}>{l.text}</span>{e.name}</span></td>
                <td className="num">{e.calls}</td><td className="num">{pct(e.resolved)}</td><td className="num">{sat(e.satisfaction)}</td>
                <td className="num">{pct(e.negative)}</td><td className="num">{pct(e.repeat)}</td></tr> })}</tbody></table></div>
          </Widget></div>}

          <Modal open={open === 'trend'} onClose={() => setOpen(null)} icon={BarChart3} title="Calls and resolution" sub="Per day in this period">
            <Trend data={data.trend} height={380} onDay={d => calls({ date_from: d, date_to: d, period: 'custom' })} />
            <table className="table"><thead><tr><th>Day</th><th className="num">Calls</th><th className="num">Fully resolved</th><th className="num">Satisfaction</th><th className="num">Ended unhappy</th></tr></thead>
              <tbody>{[...data.trend].reverse().filter((d: any) => d.calls).map((d: any) => <tr key={d.date} className="click" onClick={() => calls({ date_from: d.date, date_to: d.date, period: 'custom' })}>
                <td>{d.date}</td><td className="num">{d.calls}</td><td className="num">{pct(d.resolved)}</td><td className="num">{sat(d.satisfaction)}</td><td className="num">{pct(d.negative)}</td></tr>)}</tbody></table>
          </Modal>
          <Modal open={open === 'reasons'} onClose={() => setOpen(null)} icon={Tags} title="Why customers call" sub="Every reason in this period">
            <table className="table"><thead><tr><th>Reason</th><th className="num">Calls</th><th className="num">Resolved</th><th className="num">Not resolved</th><th className="num">Satisfaction</th><th className="num">Repeat</th><th></th></tr></thead>
              <tbody>{data.reasons.map((r: any) => <tr key={r.code} className="click" onClick={() => calls({ reason: r.code })}>
                <td>{r.name}</td><td className="num">{r.calls}</td><td className="num">{pct(r.resolved)}</td>
                <td className="num" style={{ color: (r.not_resolved || 0) > 0.3 ? 'var(--neg-text)' : undefined }}>{pct(r.not_resolved)}</td>
                <td className="num">{sat(r.satisfaction)}</td><td className="num">{pct(r.repeat)}</td>
                <td><button className="btn sm" onClick={e => { e.stopPropagation(); calls({ reason: r.code, resolution: 'partly_resolved,not_resolved' }) }}>Open calls</button></td></tr>)}</tbody></table>
          </Modal>
          <Modal open={open === 'agents'} onClose={() => setOpen(null)} icon={Users} title="All agents" sub="This period">
            <AgentTable agents={data.agents} list={list} showEnt={ent === 'all'} onPick={id => nav(`${base}/agents/${id}`)} full />
          </Modal>
          <Modal open={open === 'mood'} onClose={() => setOpen(null)} icon={Workflow} title="Customer mood journey" sub="How the customer's mood changed between the start and the end of the call">
            <Chart height={420} option={() => sankey(data.mood_flow)} />
          </Modal>
        </>}
      </div>
    </>
  )
}

function Tile({ n, label, onClick }: { n: number; label: string; onClick: () => void }) {
  return <button className="card" style={{ padding: 12, textAlign: 'left', cursor: 'pointer' }} onClick={onClick}>
    <div style={{ font: '500 20px/28px var(--font)' }} className="num">{n}</div><div className="tiny muted">{label}</div></button>
}

/** Bar + line combo (guidelines): bars #DDD6FE, the highlighted period #6366F1, the overlay line orange. */
function Trend({ data, height = 230, onDay }: { data: any[]; height?: number; onDay?: (d: string) => void }) {
  const cut = data.length - 7
  return <Chart height={height} onClick={e => onDay?.(data[e.dataIndex]?.date)} option={t => ({
    grid: { left: 32, right: 44, top: 12, bottom: 26 },
    xAxis: { type: 'category', data: data.map(d => d.date), ...axis(t), splitLine: { show: false },
      axisLabel: { color: t.faint, fontSize: 12, formatter: (v: string) => new Date(v).toLocaleDateString('en', { month: 'short', day: 'numeric' }).toUpperCase() } },
    yAxis: [{ type: 'value', minInterval: 1, ...axis(t) },
      { type: 'value', min: 0, max: 1, axisLabel: { formatter: (v: number) => `${v * 100}%`, color: t.faint, fontSize: 12 }, splitLine: { show: false } }],
    tooltip: { valueFormatter: (v: any) => (typeof v === 'number' && v <= 1 && !Number.isInteger(v) ? `${Math.round(v * 100)}%` : v) },
    series: [
      { name: 'Calls', type: 'bar', barMaxWidth: 16, data: data.map((d, i) => ({ value: d.calls, itemStyle: { color: i >= cut ? cssVar('--bar-hi') : cssVar('--bar'), borderRadius: [2, 2, 0, 0] } })) },
      { name: 'Fully resolved', type: 'line', yAxisIndex: 1, smooth: 0.35, smoothMonotone: 'x', symbol: 'circle', symbolSize: 5, connectNulls: true,
        data: data.map(d => (d.calls ? d.resolved : null)), lineStyle: { width: 2, color: '#F59E0C' }, itemStyle: { color: '#F59E0C' },
        areaStyle: { color: 'rgba(245,158,12,.06)' } },
    ],
  })} />
}

function Ended({ res, total, flow, onPick }: { res: Record<string, number>; total: number; flow: any[]; onPick: (r: string) => void }) {
  let better = 0, n = 0
  for (const r of flow) { n += r.calls; if ((MOODS[r.to]?.score ?? 0) > (MOODS[r.from]?.score ?? 0)) better += r.calls }
  const color: Record<string, string> = { resolved: 'var(--pos-accent)', partly_resolved: 'var(--warn-accent)', not_resolved: 'var(--neg-accent)' }
  return <div className="stack" style={{ gap: 4 }}>
    <div className="bar" style={{ height: 8, margin: '4px 0 10px' }}>{Object.keys(RESOLUTION).map(key => <span key={key} style={{ width: `${(100 * (res[key] || 0)) / Math.max(1, total)}%`, background: color[key] }} />)}</div>
    {Object.entries(RESOLUTION).map(([key, r]) => { const I = r.icon; return <button key={key} className="bar-row click" style={{ border: 0, background: 'none', gridTemplateColumns: '1fr auto auto', textAlign: 'left', borderTop: '1px solid var(--border-light)', borderRadius: 0 }} onClick={() => onPick(key)}>
      <span className={`pill ${r.tone}`} style={{ justifySelf: 'start' }}><I size={13} />{r.label}</span><b className="num">{res[key] || 0}</b><span className="muted num" style={{ width: 40, textAlign: 'right' }}>{pct((res[key] || 0) / Math.max(1, total))}</span></button> })}
    <div className="row small" style={{ borderTop: '1px solid var(--border-light)', paddingTop: 10 }}><span className="muted">Mood improved during the call</span><span className="chg up right">{pct(n ? better / n : 0)}</span></div>
  </div>
}

function ReasonBars({ reasons, onPick }: { reasons: any[]; onPick: (c: string) => void }) {
  return <BarList onClick={onPick} rows={reasons.map(r => ({
    key: r.code, label: r.name, value: r.calls,
    right: <span>{r.calls} <span className="faint">· {pct(1 - (r.resolved || 0))} not fully resolved</span></span>,
    parts: [{ v: r.calls * (r.resolved || 0), color: 'var(--pos-accent)', title: 'resolved' },
      { v: r.calls * (1 - (r.resolved || 0) - (r.not_resolved || 0)), color: 'var(--warn-accent)', title: 'partly resolved' },
      { v: r.calls * (r.not_resolved || 0), color: 'var(--neg-accent)', title: 'not resolved' }],
  }))} />
}

function AgentTable({ agents, list, showEnt, onPick, full }: { agents: any[]; list: any[]; showEnt: boolean; onPick: (id: string) => void; full?: boolean }) {
  return <div className="table-wrap"><table className="table"><thead><tr><th>Agent</th>{showEnt && <th>Enterprise</th>}<th className="num">Calls</th><th>Fully resolved</th>
    <th className="num">Satisfaction</th><th className="num">Ended unhappy</th>{full && <th className="num">QA</th>}</tr></thead>
    <tbody>{agents.map(a => { const e = list.find(x => x.id === a.enterprise); const l = entLogo(e); return <tr key={a.id} className="click" onClick={() => onPick(a.id)}>
      <td><span className="row" style={{ gap: 8, flexWrap: 'nowrap' }}><span className="avatar">{a.name.split(/\s+/).map((w: string) => w[0]).join('').slice(0, 2)}</span><span dir="auto">{a.name}</span></span></td>
      {showEnt && <td><span className="row" style={{ gap: 8, flexWrap: 'nowrap' }}><span className="org" style={{ background: l.bg, width: 20, height: 20, fontSize: 8 }}>{l.text}</span>{e?.name ?? a.enterprise}</span></td>}
      <td className="num">{a.calls}</td>
      <td><div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}><div className="bar" style={{ width: 80, height: 6 }}><span style={{ width: `${(a.resolved || 0) * 100}%`, background: (a.resolved || 0) >= .85 ? 'var(--pos-accent)' : 'var(--neutral-accent)' }} /></div><span className="num">{pct(a.resolved)}</span></div></td>
      <td className="num">{sat(a.satisfaction)}</td><td className="num">{pct(a.negative)}</td>{full && <td className="num">{a.qa ?? '–'}</td>}</tr> })}</tbody></table></div>
}

const MOOD_ORDER = ['angry', 'frustrated', 'worried', 'confused', 'calm', 'happy']
function MoodJourney({ flow, onPick }: { flow: any[]; onPick: (to: string) => void }) {
  const start: Record<string, number> = {}, end: Record<string, number> = {}
  let better = 0, worse = 0, total = 0
  for (const r of flow) {
    start[r.from] = (start[r.from] || 0) + r.calls; end[r.to] = (end[r.to] || 0) + r.calls; total += r.calls
    const d = (MOODS[r.to]?.score ?? 0) - (MOODS[r.from]?.score ?? 0)
    if (d > 0) better += r.calls; else if (d < 0) worse += r.calls
  }
  const tone: Record<string, string> = { good: 'var(--pos-accent)', bad: 'var(--neg-accent)', warn: 'var(--warn-accent)', info: 'var(--info-accent)' }
  const col = (m: Record<string, number>, click?: boolean) => <div className="stack" style={{ gap: 6 }}>{MOOD_ORDER.filter(x => m[x]).map(x => {
    const M = MOODS[x]; const I = M.icon
    return <button key={x} className="row small" style={{ border: 0, background: 'none', padding: 0, cursor: click ? 'pointer' : 'default', flexWrap: 'nowrap' }} onClick={() => click && onPick(x)}>
      <span className={`pill ${M.tone}`} style={{ width: 104 }}><I size={13} />{M.label}</span>
      <div className="bar" style={{ width: 64, height: 6 }}><span style={{ width: `${(100 * m[x]) / total}%`, background: tone[M.tone] }} /></div>
      <span className="num">{m[x]}</span></button>
  })}</div>
  return <div className="stack">
    <div className="grid g2" style={{ gap: 16 }}><div><div className="overline" style={{ marginBottom: 8 }}>At the start</div>{col(start)}</div>
      <div><div className="overline" style={{ marginBottom: 8 }}>At the end</div>{col(end, true)}</div></div>
    <div className="row small"><span className="chg up">{pct(total ? better / total : 0)} improved</span><span className="chg down">{pct(total ? worse / total : 0)} got worse</span></div>
  </div>
}

function sankey(flow: any[]) {
  const nodes = new Set<string>()
  const links = flow.map(r => { nodes.add(`Start: ${r.from}`); nodes.add(`End: ${r.to}`); return { source: `Start: ${r.from}`, target: `End: ${r.to}`, value: r.calls } })
  return { tooltip: { trigger: 'item' }, series: [{ type: 'sankey', data: [...nodes].map(name => ({ name })), links, emphasis: { focus: 'adjacency' },
    lineStyle: { color: 'gradient', opacity: 0.35 }, label: { fontSize: 12 }, nodeGap: 14 }] }
}

const DAYS = ['Sat', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri']
function Heat({ grid }: { grid: number[][] }) {
  const max = Math.max(1, ...grid.flat())
  return <div className="heat" role="img" aria-label="Calls by weekday and hour">
    <span />{[...Array(24)].map((_, h) => <span key={h} style={{ textAlign: 'center' }}>{h % 3 === 0 ? h : ''}</span>)}
    {grid.map((row, d) => <Fragment key={d}><span>{DAYS[d]}</span>{row.map((v, h) => <div key={`${d}-${h}`} className="c" title={`${DAYS[d]} ${h}:00 · ${v} calls`}
      style={{ background: v ? `color-mix(in srgb, #6366F1 ${18 + 82 * v / max}%, var(--bg-secondary))` : 'var(--bg-secondary)' }} />)}</Fragment>)}
  </div>
}
