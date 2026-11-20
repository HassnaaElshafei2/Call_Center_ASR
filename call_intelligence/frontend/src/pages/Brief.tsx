import { useQuery } from '@tanstack/react-query'
import { FileText, Printer } from 'lucide-react'
import { api } from '@/lib/api'
import { useFilters } from '@/lib/filters'
import { pct, sat } from '@/lib/format'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { Rich, Skeleton, Widget } from '@/components/ui'

/** One-page management brief: computed numbers, written up by the model (which may only use these numbers). */
export default function Brief() {
  const { ent, current } = useEnt()
  const { f, set } = useFilters({ period: '7d' })
  const { data, isLoading } = useQuery({ queryKey: ['brief', ent, f.period], queryFn: () => api(`/e/${ent}/brief?period=${f.period}`), staleTime: 300_000 })
  useScreen({ page: 'weekly brief', title: 'Management brief', period: f.period })
  const k = data?.facts?.kpis
  return (
    <>
      <Topbar title="Management brief" crumb="One page for leadership" actions={<button className="btn" onClick={() => print()}><Printer size={15} />Print</button>} />
      <div className="content" style={{ maxWidth: 980 }}>
        <div className="tabs" style={{ alignSelf: 'flex-start' }}>{[['7d', 'Last 7 days'], ['30d', 'Last 30 days'], ['90d', 'Last 90 days']].map(([v, l]) =>
          <button key={v} className={f.period === v ? 'on' : ''} onClick={() => set({ period: v })}>{l}</button>)}</div>
        {isLoading || !data ? <Skeleton h={500} /> : <>
          <div className="grid g4">
            {[['Calls', k.calls], ['Resolved', pct(k.resolved)], ['Satisfaction', sat(k.satisfaction)], ['Ended unhappy', pct(k.negative)]].map(([l, v]) =>
              <div key={l as string} className="card widget"><span className="seg-label">{l}</span><span className="hero-num num">{v}</span></div>)}
          </div>
          <Widget icon={FileText} title={`${current?.name ?? 'All enterprises'}: ${({ '7d': 'the last 7 days', '30d': 'the last 30 days', '90d': 'the last 90 days' } as any)[f.period || '7d']}`}
            sub={data.text ? 'Written from the computed numbers below' : 'The language model is not available, so here are the computed facts'}>
            {data.text ? <div className="stack" style={{ gap: 6 }}>{data.text.split('\n').filter((l: string) => l.trim()).map((l: string, i: number) =>
              /^#+\s/.test(l) ? <h3 key={i} style={{ fontSize: 15, marginTop: 8 }}>{l.replace(/^#+\s*/, '')}</h3>
                : /^\s*[-*]\s/.test(l) ? <div key={i} className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}><span>•</span><span><Rich text={l.replace(/^\s*[-*]\s/, '')} /></span></div>
                  : <p key={i} style={{ margin: 0 }}><Rich text={l} /></p>)}</div>
              : <ul>{data.facts.insights.map((x: string, i: number) => <li key={i}><Rich text={x} /></li>)}</ul>}
          </Widget>
          <Widget title="Top reasons" icon={FileText}>
            <table className="table"><thead><tr><th>Reason</th><th>Calls</th><th>Resolved</th><th>Satisfaction</th></tr></thead>
              <tbody>{data.facts.top_reasons.map((r: any) => <tr key={r.code}><td>{r.name}</td><td className="num">{r.calls}</td><td className="num">{pct(r.resolved)}</td><td className="num">{sat(r.satisfaction)}</td></tr>)}</tbody></table>
          </Widget>
        </>}
      </div>
    </>
  )
}
