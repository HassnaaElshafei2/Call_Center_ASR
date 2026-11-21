import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Users } from '@/components/icons'
import { api } from '@/lib/api'
import { toQuery, useFilters } from '@/lib/filters'
import { pct, sat } from '@/lib/format'
import { FilterBar } from '@/components/FilterBar'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { Empty, Skeleton } from '@/components/ui'

function Cmp({ v, team, fmt, goodUp = true }: { v: number | null; team: number | null; fmt: (x: any) => string; goodUp?: boolean }) {
  if (v == null) return <span className="faint">–</span>
  const better = team == null ? null : goodUp ? v > team + 0.02 : v < team - 0.02
  const worse = team == null ? null : goodUp ? v < team - 0.02 : v > team + 0.02
  return <span className="num" style={{ color: better ? 'var(--good)' : worse ? 'var(--bad)' : undefined, fontWeight: better || worse ? 700 : 500 }}>{fmt(v)}</span>
}

export default function Agents() {
  const { ent, base } = useEnt()
  const { f, set, clear } = useFilters()
  const nav = useNavigate()
  const { data, isLoading } = useQuery({ queryKey: ['agents', ent, f], queryFn: () => api(`/e/${ent}/agents${toQuery(f)}`) })
  useScreen({ page: 'agents', title: 'Agents', filters: f })
  const team = data?.team
  const rows = (data?.agents || []).filter((a: any) => a.calls).sort((a: any, b: any) => (b.resolved ?? 0) - (a.resolved ?? 0))
  return (
    <>
      <Topbar title="Agents" crumb="Performance and coaching" />
      <div className="content">
        <FilterBar f={f} set={set} clear={clear} show={['period']} />
        <section className="card">
          {isLoading ? <div style={{ padding: 18 }}><Skeleton h={300} /></div> : !rows.length ? <Empty icon={Users} title="No agent has analysed calls in this period" /> :
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Agent</th>{ent === 'all' && <th>Enterprise</th>}<th>Team</th><th>Calls</th><th>Resolved</th><th>Satisfaction</th><th>Ended unhappy</th><th>Calmed upset customers</th><th>Talk share</th><th>QA</th></tr></thead>
              <tbody>
                <tr style={{ background: 'var(--panel-2)' }}><td><b>Everyone</b></td>{ent === 'all' && <td />}<td /><td className="num">{team.calls}</td><td className="num">{pct(team.resolved)}</td>
                  <td className="num">{sat(team.satisfaction)}</td><td className="num">{pct(team.negative)}</td><td /><td /><td className="num">{team.qa ?? '–'}</td></tr>
                {rows.map((a: any) => <tr key={a.id} className="click" onClick={() => nav(`${base}/agents/${a.id}${toQuery({ period: f.period })}`)}>
                  <td><b>{a.name}</b></td>{ent === 'all' && <td><span className="pill plain">{a.enterprise.toUpperCase()}</span></td>}<td className="small muted">{a.team}</td>
                  <td className="num">{a.calls}</td><td><Cmp v={a.resolved} team={team.resolved} fmt={pct} /></td><td><Cmp v={a.satisfaction} team={team.satisfaction} fmt={sat} /></td>
                  <td><Cmp v={a.negative} team={team.negative} fmt={pct} goodUp={false} /></td><td className="num">{a.turnaround == null ? '–' : pct(a.turnaround)}</td>
                  <td className="num">{pct(a.talk_share)}</td><td><Cmp v={a.qa} team={team.qa} fmt={x => String(x)} /></td></tr>)}
              </tbody></table></div>}
        </section>
        <p className="small muted">Green and red mark a clear difference from everyone's average. "Calmed upset customers": calls that started worried, frustrated or angry and ended calm or happy.</p>
      </div>
    </>
  )
}
