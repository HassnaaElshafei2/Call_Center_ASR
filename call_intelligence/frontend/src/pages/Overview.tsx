import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertOctagon, CalendarClock, CheckCircle2, Clock3, Flame, Frown, Headphones, Lightbulb, ListTodo, Repeat2,
  Smile, Sparkles, Trophy, Workflow, Building2 } from 'lucide-react'
import { api } from '@/lib/api'
import { toQuery, useFilters, type Filters } from '@/lib/filters'
import { dur, num, pct, sat } from '@/lib/format'
import { Chart, axis } from '@/components/Chart'
import { FilterBar } from '@/components/FilterBar'
import { MOODS, RESOLUTION } from '@/components/labels'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { BarList, Empty, Kpi, Modal, Rich, Skeleton, Widget } from '@/components/ui'

export default function Overview() {
  const { ent, base } = useEnt()
  const { f, set, clear } = useFilters()
  const nav = useNavigate()
  const [open, setOpen] = useState<string | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['overview', ent, f], queryFn: () => api(`/e/${ent}/overview${toQuery(f)}`) })
  useScreen({ page: 'overview', title: 'Overview dashboard', filters: f, kpis: data?.kpis })
  const calls = (extra: Filters) => nav(`${base}/calls${toQuery({ ...f, ...extra })}`)
  const k = data?.kpis, p = data?.previous
  const ch = (key: string, scale = 100, unit = ' pts') => {
    if (!k || !p || k[key] == null || p[key] == null) return undefined
    const d = k[key] - p[key]
    return { value: d, label: `${d > 0 ? '+' : ''}${(d * scale).toFixed(scale === 100 ? 0 : 1)}${unit}` }
  }
  return (
    <>
      <Topbar title="Overview" crumb="Call intelligence" />
      <div className="content">
        <FilterBar f={f} set={set} clear={clear} />
        {isLoading || !data ? <div className="grid g6">{[...Array(6)].map((_, i) => <Skeleton key={i} h={130} />)}</div> : !k.calls ? (
          <div className="card"><Empty icon={Headphones} title="No analysed calls in this period">Upload calls or choose a longer period.</Empty></div>
        ) : <>
          <div className="grid g6">
            <Kpi icon={Headphones} label="Calls analysed" value={num(k.calls)} foot={p ? `vs ${num(p.calls)} before` : 'in this period'}
              change={p ? { value: k.calls - p.calls, label: `${k.calls - p.calls >= 0 ? '+' : ''}${k.calls - p.calls}` } : undefined} />
            <Kpi icon={CheckCircle2} label="Resolved" value={pct(k.resolved)} bar={k.resolved} tint="var(--good-bg)" ink="var(--good)"
              foot={`${pct(k.partly_resolved)} partly`} change={ch('resolved')} onClick={() => calls({ resolution: 'resolved' })} />
            <Kpi icon={Smile} label="Predicted satisfaction" value={<>{sat(k.satisfaction)}<span className="muted" style={{ fontSize: 16 }}> /5</span></>}
              bar={k.satisfaction ? k.satisfaction / 5 : null} tint="#f7ead0" ink="var(--gold-text)" change={ch('satisfaction', 1, '')} foot="from the conversation" />
            <Kpi icon={Frown} label="Ended unhappy" value={pct(k.negative)} bar={k.negative} tint="var(--bad-bg)" ink="var(--bad)" goodWhenUp={false}
              change={ch('negative')} foot="angry or frustrated" onClick={() => calls({ mood_end: 'angry,frustrated' })} />
            <Kpi icon={Repeat2} label="Repeat calls" value={pct(k.repeat)} bar={k.repeat} tint="var(--info-bg)" ink="var(--info)" goodWhenUp={false}
              change={ch('repeat')} foot="same issue within 14 days" onClick={() => calls({ repeat: 'true' })} />
            <Kpi icon={Clock3} label="Average call" value={dur(k.avg_duration_s)} foot={k.qa != null ? `QA score ${k.qa}` : ''} tint="var(--brand-soft)" />
          </div>

          <div className="split">
            <Widget icon={Activity} title="Calls and outcomes over time" sub="Bars: calls per day · lines: resolved share and predicted satisfaction" onExpand={() => setOpen('trend')}>
              <Trend data={data.trend} />
            </Widget>
            <Widget icon={Lightbulb} title="What we see" sub="Worked out from this period's calls; click to see them">
              {data.insights.length ? <div className="stack" style={{ gap: 2 }}>{data.insights.map((i: any, n: number) => (
                <div key={n} className={`insight ${i.severity}`} onClick={() => i.link ? nav(`${base}/${i.link}`) : calls(i.filter)}>
                  <span className="n">{n + 1}</span><p><Rich text={i.text} /></p>
                </div>))}</div> : <span className="muted small">Nothing unusual in this period.</span>}
            </Widget>
          </div>

          <div className="grid g3">
            <Widget icon={CheckCircle2} title="How calls ended" sub="Resolution, from what was said">
              <Chart height={210} onClick={(e: any) => calls({ resolution: e.data.key })} option={t => ({
                tooltip: { trigger: 'item' },
                series: [{ type: 'pie', radius: ['58%', '82%'], padAngle: 2, itemStyle: { borderRadius: 6, borderColor: t.panel, borderWidth: 2 },
                  label: { show: false }, data: Object.entries(RESOLUTION).map(([key, r]) => ({ key, name: r.label, value: data.resolution[key] || 0,
                    itemStyle: { color: key === 'resolved' ? '#12733a' : key === 'partly_resolved' ? '#c89a3a' : '#c0392b' } })) }],
              })} />
              <div className="legend">{Object.entries(RESOLUTION).map(([key, r]) => { const I = r.icon; return <span key={key}><I size={13} color={r.color} />{r.label} <b className="num">{data.resolution[key] || 0}</b></span> })}</div>
            </Widget>
            <Widget icon={Workflow} title="Customer mood journey" sub="Mood at the start → at the end of the call" onExpand={() => setOpen('mood')}>
              <MoodJourney flow={data.mood_flow} onPick={(to: string) => calls({ mood_end: to })} />
            </Widget>
            <Widget icon={ListTodo} title="Follow-up work" sub="From the Action Center">
              <div className="grid g3" style={{ gap: 10 }}>
                <Tile n={data.work.open_actions} label="Open actions" onClick={() => nav(`${base}/actions`)} />
                <Tile n={data.work.promises_due} label="Promises due" tone="var(--warn)" onClick={() => nav(`${base}/actions?tab=promises`)} />
                <Tile n={data.work.recovered} label="Customers recovered" tone="var(--good)" onClick={() => nav(`${base}/actions?tab=done`)} />
              </div>
              <div className="divider" />
              <div className="row small"><AlertOctagon size={15} className="down" /><span><b>{k.needs_review}</b> calls need a human review</span>
                <button className="btn sm right" onClick={() => nav(`${base}/review`)}>Review</button></div>
              <div className="row small"><Flame size={15} className="down" /><span><b>{k.churn_high}</b> customers at high churn risk</span>
                <button className="btn sm right" onClick={() => nav(`${base}/customers?risk=high`)}>See</button></div>
            </Widget>
          </div>

          <div className="grid g2">
            <Widget icon={Sparkles} title="Why customers call" sub="Top reasons, coloured by how they ended · click a reason" onExpand={() => setOpen('reasons')}>
              <ReasonBars reasons={data.reasons.slice(0, 8)} onPick={code => calls({ reason: code })} />
            </Widget>
            <Widget icon={Trophy} title="Agents" sub="Ranked by resolution, then satisfaction" onExpand={() => setOpen('agents')}>
              <AgentTable agents={data.agents.slice(0, 7)} onPick={id => nav(`${base}/agents/${id}${toQuery({ period: f.period })}`)} />
            </Widget>
          </div>

          <div className={`grid ${data.enterprises.length ? 'g2' : ''}`}>
            <Widget icon={CalendarClock} title="When calls come in" sub="Calls by weekday and hour (Cairo time)">
              <Heat grid={data.heatmap} />
            </Widget>
            {!!data.enterprises.length && <Widget icon={Building2} title="Enterprises side by side" sub="Same period, same measures">
              <table className="table"><thead><tr><th>Enterprise</th><th>Calls</th><th>Resolved</th><th>Satisfaction</th><th>Ended unhappy</th><th>Repeat</th></tr></thead>
                <tbody>{data.enterprises.map((e: any) => <tr key={e.id} className="click" onClick={() => nav(`/e/${e.id}/overview${toQuery(f)}`)}>
                  <td><span className="row" style={{ gap: 8 }}><span className="dot" style={{ background: e.accent }} /><b>{e.name}</b></span></td>
                  <td className="num">{e.calls}</td><td className="num">{pct(e.resolved)}</td><td className="num">{sat(e.satisfaction)}</td>
                  <td className="num">{pct(e.negative)}</td><td className="num">{pct(e.repeat)}</td></tr>)}</tbody></table>
            </Widget>}
          </div>

          <Modal open={open === 'trend'} onClose={() => setOpen(null)} icon={Activity} title="Calls and outcomes over time" sub="Per day in this period">
            <Trend data={data.trend} height={380} />
            <table className="table"><thead><tr><th>Day</th><th>Calls</th><th>Resolved</th><th>Satisfaction</th><th>Ended unhappy</th></tr></thead>
              <tbody>{[...data.trend].reverse().filter((d: any) => d.calls).map((d: any) => <tr key={d.date} className="click" onClick={() => calls({ date_from: d.date, date_to: d.date, period: 'custom' })}>
                <td>{d.date}</td><td className="num">{d.calls}</td><td className="num">{pct(d.resolved)}</td><td className="num">{sat(d.satisfaction)}</td><td className="num">{pct(d.negative)}</td></tr>)}</tbody></table>
          </Modal>
          <Modal open={open === 'reasons'} onClose={() => setOpen(null)} icon={Sparkles} title="Why customers call" sub="Every reason in this period">
            <table className="table"><thead><tr><th>Reason</th><th>Calls</th><th>Resolved</th><th>Not resolved</th><th>Satisfaction</th><th>Repeat</th><th></th></tr></thead>
              <tbody>{data.reasons.map((r: any) => <tr key={r.code} className="click" onClick={() => calls({ reason: r.code })}>
                <td><b>{r.name}</b></td><td className="num">{r.calls}</td><td className="num">{pct(r.resolved)}</td>
                <td className="num" style={{ color: (r.not_resolved || 0) > 0.3 ? 'var(--bad)' : undefined }}>{pct(r.not_resolved)}</td>
                <td className="num">{sat(r.satisfaction)}</td><td className="num">{pct(r.repeat)}</td>
                <td><button className="btn sm" onClick={e => { e.stopPropagation(); calls({ reason: r.code, resolution: 'not_resolved' }) }}>Unresolved calls</button></td></tr>)}</tbody></table>
          </Modal>
          <Modal open={open === 'agents'} onClose={() => setOpen(null)} icon={Trophy} title="All agents" sub="This period">
            <AgentTable agents={data.agents} onPick={id => nav(`${base}/agents/${id}`)} full />
          </Modal>
          <Modal open={open === 'mood'} onClose={() => setOpen(null)} icon={Workflow} title="Customer mood journey" sub="How the customer's mood changed between the start and the end of the call">
            <Chart height={420} option={() => sankey(data.mood_flow)} />
          </Modal>
        </>}
      </div>
    </>
  )
}

function Tile({ n, label, tone = 'var(--brand-text)', onClick }: { n: number; label: string; tone?: string; onClick: () => void }) {
  return <button className="card" style={{ padding: 12, textAlign: 'left', cursor: 'pointer', boxShadow: 'none' }} onClick={onClick}>
    <div className="hero-num num" style={{ fontSize: 30, color: tone }}>{n}</div><div className="small muted">{label}</div></button>
}

function Trend({ data, height = 260 }: { data: any[]; height?: number }) {
  return <Chart height={height} option={t => ({
    grid: { left: 36, right: 40, top: 20, bottom: 28 },
    xAxis: { type: 'category', data: data.map(d => d.date.slice(5)), ...axis(t), splitLine: { show: false } },
    yAxis: [{ type: 'value', minInterval: 1, ...axis(t) }, { type: 'value', min: 0, max: 1, axisLabel: { formatter: (v: number) => `${v * 100}%`, color: t.muted, fontSize: 11 }, splitLine: { show: false } }],
    tooltip: { valueFormatter: (v: any) => (typeof v === 'number' && v <= 1 && v > 0 && !Number.isInteger(v) ? `${Math.round(v * 100)}%` : v) },
    series: [
      { name: 'Calls', type: 'bar', data: data.map(d => d.calls), barMaxWidth: 14, itemStyle: { borderRadius: [4, 4, 0, 0], color: t.colors[0], opacity: 0.35 } },
      { name: 'Resolved', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'none', connectNulls: true, data: data.map(d => d.resolved), lineStyle: { width: 2.5 }, itemStyle: { color: '#12733a' } },
      { name: 'Satisfaction (÷5)', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'none', connectNulls: true, data: data.map(d => (d.satisfaction ? d.satisfaction / 5 : null)), lineStyle: { width: 2.5, type: 'dashed' }, itemStyle: { color: t.colors[3] } },
    ],
    legend: { bottom: 0, textStyle: { color: t.muted }, itemHeight: 8, show: height > 300 },
  })} />
}

function ReasonBars({ reasons, onPick }: { reasons: any[]; onPick: (c: string) => void }) {
  return <BarList onClick={onPick} rows={reasons.map(r => ({
    key: r.code, label: r.name, value: r.calls,
    right: <span>{r.calls} <span className="faint">· {pct(r.not_resolved)} unresolved</span></span>,
    parts: [{ v: r.calls * (r.resolved || 0), color: 'var(--good)', title: 'resolved' },
      { v: r.calls * (1 - (r.resolved || 0) - (r.not_resolved || 0)), color: 'var(--gold)', title: 'partly resolved' },
      { v: r.calls * (r.not_resolved || 0), color: 'var(--bad)', title: 'not resolved' }],
  }))} />
}

function AgentTable({ agents, onPick, full }: { agents: any[]; onPick: (id: string) => void; full?: boolean }) {
  return <div className="table-wrap"><table className="table"><thead><tr><th>#</th><th>Agent</th><th>Calls</th><th>Resolved</th><th>Satisfaction</th>{full && <><th>Ended unhappy</th><th>QA</th></>}</tr></thead>
    <tbody>{agents.map((a, i) => <tr key={a.id} className="click" onClick={() => onPick(a.id)}>
      <td className="faint num">{i + 1}</td><td><b>{a.name}</b></td><td className="num">{a.calls}</td>
      <td><div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}><div className="bar" style={{ width: 70 }}><span style={{ width: `${(a.resolved || 0) * 100}%`, background: 'var(--good)' }} /></div><span className="num small">{pct(a.resolved)}</span></div></td>
      <td className="num">{sat(a.satisfaction)}</td>{full && <><td className="num">{pct(a.negative)}</td><td className="num">{a.qa ?? '–'}</td></>}</tr>)}</tbody></table></div>
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
  const col = (m: Record<string, number>, click?: boolean) => <div className="stack" style={{ gap: 6 }}>{MOOD_ORDER.filter(x => m[x]).map(x => {
    const M = MOODS[x]; const I = M.icon
    return <button key={x} className="row small" style={{ border: 0, background: 'none', padding: 0, cursor: click ? 'pointer' : 'default', flexWrap: 'nowrap' }} onClick={() => click && onPick(x)}>
      <span className={`pill ${M.tone}`} style={{ width: 110 }}><I size={12} />{M.label}</span>
      <div className="bar" style={{ width: 60 }}><span style={{ width: `${(100 * m[x]) / total}%`, background: `var(--${M.tone === 'good' ? 'good' : M.tone === 'bad' ? 'bad' : M.tone === 'warn' ? 'gold' : 'info'})` }} /></div>
      <span className="num">{m[x]}</span></button>
  })}</div>
  return <div className="stack">
    <div className="grid g2" style={{ gap: 12 }}><div><div className="seg-label" style={{ marginBottom: 6 }}>At the start</div>{col(start)}</div>
      <div><div className="seg-label" style={{ marginBottom: 6 }}>At the end</div>{col(end, true)}</div></div>
    <div className="row small"><span className="pill good">{pct(total ? better / total : 0)} improved</span><span className="pill bad">{pct(total ? worse / total : 0)} got worse</span></div>
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
    {grid.map((row, d) => <>{<span key={`l${d}`}>{DAYS[d]}</span>}{row.map((v, h) => <div key={`${d}-${h}`} className="c" title={`${DAYS[d]} ${h}:00 · ${v} calls`}
      style={{ background: v ? `color-mix(in srgb, var(--brand) ${15 + 85 * v / max}%, transparent)` : 'var(--track)' }} />)}</>)}
  </div>
}
