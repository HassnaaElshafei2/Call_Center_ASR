import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Search, UserRound, Users } from '@/components/icons'
import { api } from '@/lib/api'
import { toQuery, useFilters } from '@/lib/filters'
import { when } from '@/lib/format'
import { FilterBar } from '@/components/FilterBar'
import { ResolutionBadge, Stars } from '@/components/labels'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { Empty, Kpi, Skeleton } from '@/components/ui'

export default function Customers() {
  const { ent, base } = useEnt()
  const { f, set, clear } = useFilters({ period: '90d' })
  const nav = useNavigate()
  const { data, isLoading } = useQuery({ queryKey: ['customers', ent, f], queryFn: () => api(`/e/${ent}/customers${toQuery({ ...f, q: undefined }, { name: f.q })}`) })
  useScreen({ page: 'customers', title: 'Customers', filters: f })
  return (
    <>
      <Topbar title="Customers" crumb="Everyone who called, and who needs attention" />
      <div className="content">
        <FilterBar f={f} set={set} clear={clear} show={['period']} extra={<>
          <div className="tabs">{[['', 'Everyone'], ['high', 'At risk'], ['medium', 'Watch']].map(([k, l]) =>
            <button key={k} className={(f.risk || '') === k ? 'on' : ''} onClick={() => set({ risk: k })}>{l}</button>)}</div>
          <div className="search"><Search size={15} /><input className="input" style={{ width: 220 }} placeholder="Name or last digits" defaultValue={f.q || ''}
            onKeyDown={e => e.key === 'Enter' && set({ q: (e.target as HTMLInputElement).value })} /></div></>} />
        {data && <div className="grid g4">
          <Kpi icon={Users} label="Customers" value={data.total} foot="with analysed calls in this period" />
          <Kpi icon={AlertTriangle} label="At risk" value={data.at_risk} tint="var(--bad-bg)" ink="var(--bad)" foot="unhappy and unresolved, or may leave" onClick={() => set({ risk: 'high' })} />
        </div>}
        <section className="card">
          {isLoading ? <div style={{ padding: 18 }}><Skeleton h={300} /></div> : !data?.customers.length ? <Empty icon={UserRound} title="No customers match" /> :
            <div className="table-wrap"><table className="table"><thead><tr><th>Customer</th>{ent === 'all' && <th>Enterprise</th>}<th>Risk</th><th>Calls</th><th>Last call</th><th>Last outcome</th><th>Satisfaction</th><th>Open actions</th></tr></thead>
              <tbody>{data.customers.map((c: any) => <tr key={c.id} className="click" onClick={() => nav(`${base}/customers/${c.id}`)}>
                <td><b>{c.name}</b>{c.vip && <span className="pill brand" style={{ marginLeft: 6 }}>VIP</span>}<div className="tiny muted">{c.phone || ({ none: 'no number yet' } as any)[c.identified_by]}</div></td>
                {ent === 'all' && <td><span className="pill plain">{c.enterprise.toUpperCase()}</span></td>}
                <td>{c.risk === 'low' ? <span className="pill good">Fine</span> : <span className={`pill ${c.risk === 'high' ? 'bad' : 'warn'}`} title={c.risk_why.join('; ')}><AlertTriangle size={12} />{c.risk === 'high' ? 'At risk' : 'Watch'}</span>}
                  {c.risk !== 'low' && <div className="tiny muted clamp1" style={{ maxWidth: 220 }}>{c.risk_why.join(' · ')}</div>}</td>
                <td className="num">{c.calls}</td><td className="small">{when(c.last_call)}</td><td><ResolutionBadge value={c.last_resolution} /></td>
                <td><Stars value={c.last_satisfaction} /></td><td className="num">{c.open_actions || '–'}</td></tr>)}</tbody></table></div>}
        </section>
      </div>
    </>
  )
}
