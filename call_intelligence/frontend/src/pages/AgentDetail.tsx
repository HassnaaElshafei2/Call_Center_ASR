import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, Award, ClipboardCheck, GraduationCap, Headphones, Loader2, Smile, Sparkles, CheckCircle2 } from 'lucide-react'
import { api } from '@/lib/api'
import { toQuery, useFilters } from '@/lib/filters'
import { pct, sat, title, when } from '@/lib/format'
import { Chart, axis } from '@/components/Chart'
import { FilterBar } from '@/components/FilterBar'
import { ResolutionBadge, Stars } from '@/components/labels'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { Kpi, Skeleton, Widget } from '@/components/ui'

export default function AgentDetail() {
  const { id } = useParams()
  const { ent, base, meta } = useEnt()
  const { f, set, clear } = useFilters({ period: '90d' })
  const nav = useNavigate()
  const { data: a } = useQuery({ queryKey: ['agent', ent, id, f], queryFn: () => api(`/e/${ent}/agents/${id}${toQuery(f)}`) })
  const [coach, setCoach] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useScreen(a ? { page: 'agent', agent_id: a.id, title: `Agent ${a.name}`, kpis: a.kpis } : { page: 'agent' })
  if (!a) return <><Topbar title="Agent" /><div className="content"><Skeleton h={400} /></div></>
  const k = a.kpis, t = a.team_kpis
  const kpiName = (code: string) => (meta?.kpis || []).find((x: any) => x.code === code && x.enterprise === a.enterprise)?.name || title(code)
  const getCoaching = async () => { setBusy(true); setErr(''); try { setCoach(await api(`/e/${ent}/agents/${id}/coaching${toQuery(f)}`, { method: 'POST' })) } catch (e: any) { setErr(e.message) } finally { setBusy(false) } }
  return (
    <>
      <Topbar title={a.name} crumb={<Link to={`${base}/agents`}>Agents</Link>} />
      <div className="content">
        <FilterBar f={f} set={set} clear={clear} show={['period']} />
        <div className="grid g4">
          <Kpi icon={Headphones} label="Calls" value={k.calls} foot={`team average ${t.calls ? Math.round(t.calls / Math.max(1, (meta?.agents || []).filter((x: any) => x.enterprise === a.enterprise).length)) : '–'}`} />
          <Kpi icon={CheckCircle2} label="Resolved" value={pct(k.resolved)} bar={k.resolved} tint="var(--good-bg)" ink="var(--good)" foot={`team ${pct(t.resolved)}`} />
          <Kpi icon={Smile} label="Satisfaction" value={sat(k.satisfaction)} bar={k.satisfaction ? k.satisfaction / 5 : null} tint="#f7ead0" ink="var(--gold-text)" foot={`team ${sat(t.satisfaction)}`} />
          <Kpi icon={ClipboardCheck} label="QA score" value={k.qa ?? '–'} bar={k.qa ? k.qa / 100 : null} foot={`team ${t.qa ?? '–'}`} />
        </div>
        <div className="split">
          <Widget icon={Activity} title="Week by week" sub="Resolution and satisfaction">
            <Chart height={240} option={th => ({
              grid: { left: 36, right: 36, top: 16, bottom: 26 }, xAxis: { type: 'category', data: a.trend.map((w: any) => w.week.slice(5)), ...axis(th) },
              yAxis: [{ type: 'value', min: 0, max: 1, axisLabel: { formatter: (v: number) => `${v * 100}%`, color: th.muted }, splitLine: { lineStyle: { color: th.line } } }, { type: 'value', min: 1, max: 5, splitLine: { show: false }, axisLabel: { color: th.muted } }],
              series: [{ name: 'Resolved', type: 'bar', data: a.trend.map((w: any) => w.resolved), barMaxWidth: 22, itemStyle: { color: '#12733a', borderRadius: [4, 4, 0, 0], opacity: 0.75 } },
                { name: 'Satisfaction', type: 'line', yAxisIndex: 1, data: a.trend.map((w: any) => w.satisfaction), symbolSize: 8, lineStyle: { width: 3 }, itemStyle: { color: th.colors[3] } }] })} />
          </Widget>
          <Widget icon={GraduationCap} title="Coaching" sub="Written from this agent's numbers and failed scorecard moments"
            actions={<button className="btn sm primary" onClick={getCoaching} disabled={busy}>{busy ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />}{coach ? 'Refresh' : 'Prepare coaching'}</button>}>
            {err && <span className="pill bad">{err}</span>}
            {!coach && !busy && <span className="small muted">Prepare 3 coaching points with the call moments that show them.</span>}
            {coach && <div className="stack">
              <div className="row small" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}><Award size={16} className="up" /><span><b>Doing well:</b> {coach.strength}</span></div>
              {coach.points.map((p: any, i: number) => <div key={i} className="card" style={{ padding: 12, boxShadow: 'none' }}>
                <b>{i + 1}. {p.title}</b><div className="small muted">{p.detail}</div>
                {p.examples?.length > 0 && <div className="row" style={{ marginTop: 6 }}>{p.examples.map((x: any, j: number) => <Link key={j} className="chip" to={`${base}/calls/${x.call_id}`} title={x.note}>Example {j + 1}</Link>)}</div>}
              </div>)}
            </div>}
          </Widget>
        </div>
        <div className="grid g2">
          <Widget icon={ClipboardCheck} title="Scorecard items" sub="Pass rate, weakest first, against the team">
            {a.scorecard.map((s: any) => <div key={s.kpi} className="bar-row">
              <span><b>{kpiName(s.kpi)}</b></span><span className="num small"><b style={{ color: s.team_rate != null && s.rate < s.team_rate - 0.05 ? 'var(--bad)' : undefined }}>{pct(s.rate)}</b> <span className="faint">team {pct(s.team_rate)}</span></span>
              <div className="bar" style={{ position: 'relative' }}><span style={{ width: `${s.rate * 100}%`, background: s.rate >= (s.team_rate ?? 0) ? 'var(--good)' : 'var(--gold)' }} />
                {s.team_rate != null && <i style={{ position: 'absolute', left: `${s.team_rate * 100}%`, top: -2, bottom: -2, width: 2, background: 'var(--ink)' }} />}</div>
            </div>)}
            {!a.scorecard.length && <span className="small muted">No scored calls.</span>}
          </Widget>
          <Widget icon={Activity} title="How they talk" sub="Measured from timings">
            <dl className="kv">{Object.entries(a.behaviour).map(([key, v]: any) => <><dt key={key}>{({ agent_talk_share: 'Talk share', longest_silence_s: 'Longest silence (s)', silences_over_5s: 'Silences over 5 s per call', overlaps: 'Talking over the customer per call' } as any)[key]}</dt>
              <dd className="num">{key === 'agent_talk_share' ? pct(v.agent) : v.agent ?? '–'} <span className="faint">· team {key === 'agent_talk_share' ? pct(v.team) : v.team ?? '–'}</span></dd></>)}</dl>
          </Widget>
        </div>
        <Widget icon={Headphones} title="Recent calls">
          <table className="table"><thead><tr><th>When</th><th>Customer</th><th style={{ width: '45%' }}>What happened</th><th>Outcome</th><th>Satisfaction</th></tr></thead>
            <tbody>{a.calls.map((c: any) => <tr key={c.id} className="click" onClick={() => nav(`${base}/calls/${c.id}`)}><td className="small">{when(c.started_at)}</td><td>{c.customer?.name || '–'}</td>
              <td className="small clamp">{c.summary}</td><td><ResolutionBadge value={c.resolution} /></td><td><Stars value={c.satisfaction} /></td></tr>)}</tbody></table>
        </Widget>
      </div>
    </>
  )
}
