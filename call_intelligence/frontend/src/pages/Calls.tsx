import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ClipboardCheck, Download, Headphones, Loader2, Repeat2 } from '@/components/icons'
import { api, download } from '@/lib/api'
import { toQuery, useFilters } from '@/lib/filters'
import { dur, title, when } from '@/lib/format'
import { FilterBar } from '@/components/FilterBar'
import { ComplianceBadge, MoodBadge, ResolutionBadge, RiskBadge, Stars } from '@/components/labels'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { Empty, Skeleton } from '@/components/ui'

const STATUS: Record<string, string> = { queued: 'Queued', waiting_asr: 'Waiting for transcription', transcribing: 'Transcribing', analyzing: 'Analysing', failed: 'Failed' }

export default function Calls({ review = false }: { review?: boolean }) {
  const { ent, base, meta } = useEnt()
  const { f, set, clear } = useFilters(review ? { period: 'all', review: 'true' } : { period: '30d' })
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState('newest')
  const nav = useNavigate()
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['calls', ent, f, page, sort], placeholderData: keepPreviousData,
    queryFn: () => api(`/e/${ent}/calls${toQuery(f, { page, sort, size: 50 })}`),
    refetchInterval: q => ((q.state.data as any)?.calls?.some((c: any) => !['done', 'failed'].includes(c.status)) ? 5000 : false),
  })
  useScreen({ page: review ? 'review queue' : 'calls list', title: review ? 'Review queue' : 'Calls', filters: f, total: data?.total })
  const catName = (code: string) => (meta?.categories || []).find((c: any) => c.code === code)?.name || title(code)
  return (
    <>
      <Topbar title={review ? 'Review queue' : 'Calls'} crumb={review ? 'Calls a person should check' : 'Every call, transcribed and analysed'}
        actions={<button className="btn" onClick={() => download(`/e/${ent}/calls.csv${toQuery(f)}`, 'calls.csv')}><Download size={15} />Export</button>} />
      <div className="content">
        {review && <div className="card widget" style={{ flexDirection: 'row', alignItems: 'center' }}>
          <div className="widget-icon"><ClipboardCheck size={18} /></div>
          <div className="small"><b>Calls flagged for a person:</b> a compliance issue, a critical scorecard item failed, low transcript confidence, or the second opinion disagreed with the analysis. Open a call to approve or correct its labels; corrections are kept to improve the models.</div>
        </div>}
        <FilterBar f={f} set={p => { setPage(1); set(p) }} clear={clear} extra={
          <select className="input" style={{ width: 170 }} value={sort} onChange={e => setSort(e.target.value)} aria-label="Sort">
            <option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="satisfaction">Least satisfied first</option>
            <option value="qa">Lowest QA first</option><option value="duration">Longest first</option></select>} />
        <section className="card">
          <div className="row" style={{ padding: '14px 18px 4px' }}><b>{data?.total ?? '…'} calls</b>{isFetching && <Loader2 size={14} className="spin muted" />}</div>
          {isLoading ? <div style={{ padding: 18 }}><Skeleton h={300} /></div> : !data?.calls.length ? (
            <Empty icon={Headphones} title={review ? 'Nothing to review' : 'No calls match'}>{review ? 'Every flagged call has been checked.' : 'Try another period or fewer filters.'}</Empty>
          ) : <div className="table-wrap"><table className="table">
            <thead><tr><th>When</th>{ent === 'all' && <th>Enterprise</th>}<th>Customer</th><th>Agent</th><th style={{ width: '32%' }}>What happened</th><th>Outcome</th><th>Satisfaction</th><th>Mood at end</th><th>Length</th></tr></thead>
            <tbody>{data.calls.map((c: any) => (
              <tr key={c.id} className="click" onClick={() => nav(`${base}/calls/${c.id}`)}>
                <td className="small" style={{ whiteSpace: 'nowrap' }}>{when(c.started_at)}</td>
                {ent === 'all' && <td><span className="pill plain">{c.enterprise.toUpperCase()}</span></td>}
                <td><b className="clamp1" style={{ maxWidth: 160, display: 'block' }}>{c.customer?.name || '–'}</b><span className="tiny muted">{c.customer?.phone}</span></td>
                <td className="small">{c.agent?.name || '–'}</td>
                <td>{c.status === 'done' ? <>
                  <span className="small strong">{catName(c.reason)}</span>
                  <div className="small muted clamp">{c.summary}</div>
                  <div className="row" style={{ gap: 4, marginTop: 4 }}><RiskBadge value={c.churn_risk} /><ComplianceBadge on={c.compliance_issue} />
                    {c.repeat_of && <span className="pill info"><Repeat2 size={12} />Repeat call</span>}{c.needs_review && <span className="pill warn">Review</span>}</div>
                </> : <span className={`pill ${c.status === 'failed' ? 'bad' : 'info'}`}>{c.status !== 'failed' && c.status !== 'waiting_asr' && <Loader2 size={12} className="spin" />}{STATUS[c.status] || c.status}</span>}</td>
                <td><ResolutionBadge value={c.resolution} /></td><td><Stars value={c.satisfaction} /></td><td><MoodBadge value={c.mood_end} /></td>
                <td className="num small">{dur(c.duration_s)}</td>
              </tr>))}</tbody>
          </table></div>}
          {data && data.total > 50 && <div className="row" style={{ padding: 14 }}>
            <span className="small muted">Page {page} of {Math.ceil(data.total / 50)}</span>
            <button className="btn sm right" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
            <button className="btn sm" disabled={page * 50 >= data.total} onClick={() => setPage(p => p + 1)}>Next</button></div>}
        </section>
      </div>
    </>
  )
}
