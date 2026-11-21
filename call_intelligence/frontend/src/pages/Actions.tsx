import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, Check, CircleDollarSign, Copy, Handshake, ListTodo, Loader2, PartyPopper, Sparkles, Timer, Wand2 } from '@/components/icons'
import { api } from '@/lib/api'
import { can, useAuth } from '@/lib/auth'
import { when } from '@/lib/format'
import { ACTION_LABEL, OUTCOME_LABEL, PRIORITY_TONE, ResolutionBadge, Stars } from '@/components/labels'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { Empty, Kpi, Modal, Skeleton, useToast, Widget } from '@/components/ui'

const COLS: [string, string][] = [['suggested', 'Suggested'], ['open', 'To do'], ['in_progress', 'In progress'], ['done', 'Done']]

export default function Actions() {
  const { ent, base } = useEnt()
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') || 'board'
  const [type, setType] = useState('')
  const [mine, setMine] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['actions', ent, type, mine], queryFn: () => api(`/e/${ent}/actions?${new URLSearchParams({ ...(type ? { type } : {}), ...(mine ? { owner: 'me' } : {}) })}`) })
  const promises = useQuery({ queryKey: ['promises', ent], queryFn: () => api(`/e/${ent}/promises?status=open`), enabled: tab === 'promises' })
  useScreen({ page: 'action center', title: 'Action Center', tab })
  const s = data?.summary
  const setPromise = async (id: number, status: string) => { await api(`/e/${ent}/promises/${id}`, { method: 'PATCH', json: { status } }); qc.invalidateQueries({ queryKey: ['promises', ent] }) }
  return (
    <>
      <Topbar title="Action Center" crumb="From insight to follow-up" />
      <div className="content">
        {s && <div className="grid g4">
          <Kpi icon={ListTodo} label="Open actions" value={s.open} foot={`${s.suggested} suggested by the analysis`} />
          <Kpi icon={Timer} label="Overdue" value={s.overdue} tint="var(--bad-bg)" ink="var(--bad)" foot="past their due date" />
          <Kpi icon={PartyPopper} label="Customers recovered" value={s.recovered} tint="var(--good-bg)" ink="var(--good)" foot={`of ${s.done} finished actions`} />
          <Kpi icon={CircleDollarSign} label="Value kept" value={s.value_egp ? `${Math.round(s.value_egp).toLocaleString()} EGP` : '–'} tint="#f7ead0" ink="var(--gold-text)" foot="recorded on recovered customers" />
        </div>}
        <div className="filters">
          <div className="tabs">{[['board', 'Board'], ['promises', 'Promises to customers'], ['done', 'Outcomes']].map(([k, l]) =>
            <button key={k} className={tab === k ? 'on' : ''} onClick={() => setSp({ tab: k })}>{l}</button>)}</div>
          {tab !== 'promises' && <>
            <select className="input" style={{ width: 190 }} value={type} onChange={e => setType(e.target.value)}><option value="">Every type</option>
              {Object.entries(ACTION_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            <button className={`chip ${mine ? 'on' : ''}`} onClick={() => setMine(m => !m)}>Assigned to me</button></>}
        </div>
        {isLoading ? <Skeleton h={400} /> : tab === 'board' ? (
          <div className="kanban">{COLS.map(([st, label]) => {
            const items = (data?.actions || []).filter((a: any) => a.status === st).slice(0, st === 'done' ? 20 : 60)
            return <div key={st} className="col"><h4>{label}<span className="pill plain">{(data?.actions || []).filter((a: any) => a.status === st).length}</span></h4>
              {items.map((a: any) => <TaskCard key={a.id} a={a} ent={ent} onOpen={() => setOpen(a.id)} />)}
              {!items.length && <span className="small faint">Nothing here.</span>}</div>
          })}</div>
        ) : tab === 'promises' ? (
          <Widget icon={Handshake} title="Promises made to customers" sub="Commitments found in calls: keep them, or call before they're broken">
            {promises.isLoading ? <Skeleton /> : !promises.data?.length ? <Empty title="No open promises" /> : <table className="table"><thead><tr><th>Due</th><th>Promise</th><th>Customer</th><th>Agent</th><th></th></tr></thead>
              <tbody>{promises.data.map((p: any) => <tr key={p.id}>
                <td>{p.due ? <span className={`pill ${p.overdue ? 'bad' : p.due_today ? 'warn' : 'plain'}`}><CalendarClock size={12} />{p.overdue ? 'Overdue · ' : p.due_today ? 'Today · ' : ''}{p.due}</span> : <span className="faint">no date</span>}</td>
                <td><Link to={`${base}/calls/${p.call_id}`} className="bubble-ar" style={{ display: 'block' }}>{p.text}</Link></td>
                <td>{p.customer ? <Link to={`${base}/customers/${p.customer.id}`}><b>{p.customer.name}</b></Link> : '–'}</td><td className="small">{p.agent || '–'}</td>
                <td><div className="row" style={{ flexWrap: 'nowrap' }}><button className="btn sm" onClick={() => setPromise(p.id, 'kept')}><Check size={13} />Kept</button><button className="btn sm danger" onClick={() => setPromise(p.id, 'broken')}>Broken</button></div></td></tr>)}</tbody></table>}
          </Widget>
        ) : (
          <Widget icon={PartyPopper} title="Outcomes" sub="Finished follow-ups and what they achieved">
            <table className="table"><thead><tr><th>Finished</th><th>Action</th><th>Customer</th><th>Outcome</th><th>Value</th></tr></thead>
              <tbody>{(data?.actions || []).filter((a: any) => a.status === 'done').map((a: any) => <tr key={a.id} className="click" onClick={() => setOpen(a.id)}>
                <td className="small">{when(a.updated_at)}</td><td><b>{a.title}</b><div className="tiny muted">{ACTION_LABEL[a.type]}</div></td>
                <td>{a.customer?.name || '–'}</td><td>{a.outcome ? <span className={`pill ${['recovered', 'offer_accepted', 'resolved_later'].includes(a.outcome) ? 'good' : 'plain'}`}>{OUTCOME_LABEL[a.outcome]}</span> : '–'}</td>
                <td className="num">{a.value_egp ? `${a.value_egp.toLocaleString()} EGP` : '–'}</td></tr>)}</tbody></table>
          </Widget>
        )}
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} icon={ListTodo} title="Action" sub="Assign, draft the message, record the outcome">
        {open && <ActionEditor id={open} onSaved={() => qc.invalidateQueries({ queryKey: ['actions', ent] })} />}
      </Modal>
    </>
  )
}

function TaskCard({ a, ent, onOpen }: { a: any; ent: string; onOpen: () => void }) {
  return <div className="card task" onClick={onOpen}>
    <div className="row" style={{ gap: 6 }}><span className={`pill ${PRIORITY_TONE[a.priority]}`}>{a.priority}</span><span className="pill brand">{ACTION_LABEL[a.type] || a.type}</span>
      {ent === 'all' && <span className="pill plain">{a.enterprise.toUpperCase()}</span>}{a.overdue && <span className="pill bad right">overdue</span>}</div>
    <b className="small">{a.title}</b>
    {a.customer && <span className="small muted">{a.customer.name}{a.call && <> · <ResolutionBadge value={a.call.resolution} /></>}</span>}
    <div className="row tiny muted">{a.due && <span><CalendarClock size={11} /> {a.due}</span>}{a.draft_message && <span className="right"><Sparkles size={11} /> message {a.draft_approved ? 'approved' : 'drafted'}</span>}</div>
  </div>
}

export function ActionEditor({ id, onSaved }: { id: string; onSaved?: () => void }) {
  const { ent, base, meta } = useEnt()
  const { me } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: a, refetch } = useQuery({ queryKey: ['action', ent, id], queryFn: () => api(`/e/${ent}/actions/${id}`) })
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState('')
  const [outcome, setOutcome] = useState('')
  const [note, setNote] = useState('')
  const [value, setValue] = useState('')
  if (!a) return <Skeleton h={300} />
  const canAct = can(me, 'act', a.enterprise)
  const patch = async (body: any, label = 'Saved') => {
    setBusy(label)
    try { await api(`/e/${ent}/actions/${id}`, { method: 'PATCH', json: body }); toast(label); await refetch(); onSaved?.(); qc.invalidateQueries({ queryKey: ['call'] }) } finally { setBusy('') }
  }
  const draft = async () => { setBusy('draft'); try { await api(`/e/${ent}/actions/${id}/draft`, { method: 'POST' }); setMsg(null); await refetch() } finally { setBusy('') } }
  const text = msg ?? a.draft_message
  return <div className="stack" style={{ gap: 16 }}>
    <div className="row"><span className={`pill ${PRIORITY_TONE[a.priority]}`}>{a.priority} priority</span><span className="pill brand">{ACTION_LABEL[a.type]}</span>
      <span className="pill plain">{a.status.replace('_', ' ')}</span>{a.call_id && <Link className="btn sm right" to={`${base}/calls/${a.call_id}`}>Open the call</Link>}</div>
    <div><h3 style={{ fontSize: 18 }}>{a.title}</h3><p className="muted" style={{ margin: '4px 0 0' }}>{a.reason}</p></div>
    {canAct && <div className="grid g3" style={{ gap: 10 }}>
      <label className="field">Owner<select className="input" value={a.owner_id || ''} onChange={e => patch({ owner_id: e.target.value }, 'Assigned')}>
        <option value="">Nobody yet</option>{(meta?.users || []).map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
      <label className="field">Status<select className="input" value={a.status} onChange={e => patch({ status: e.target.value }, 'Status changed')}>
        {[['suggested', 'Suggested'], ['open', 'To do'], ['in_progress', 'In progress'], ['done', 'Done'], ['dismissed', 'Dismissed']].map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      <label className="field">Due<input className="input" type="date" value={a.due || ''} onChange={e => patch({ due: e.target.value }, 'Due date set')} /></label>
    </div>}
    <section className="card" style={{ padding: 14, boxShadow: 'none' }}>
      <div className="row"><b>Message to the customer</b>{a.draft_approved ? <span className="pill good"><Check size={12} />Approved</span> : text ? <span className="pill warn">Draft: needs approval</span> : null}
        {canAct && <button className="btn sm right" onClick={draft} disabled={!!busy}>{busy === 'draft' ? <Loader2 size={13} className="spin" /> : <Wand2 size={13} />}{text ? 'Rewrite' : 'Draft a message'}</button>}</div>
      {text ? <textarea className="input bubble-ar" rows={4} style={{ marginTop: 10, width: '100%' }} value={text} readOnly={!canAct} onChange={e => setMsg(e.target.value)} />
        : <p className="small muted">No message yet. Drafts are written in Egyptian Arabic from the call; nothing is sent without a person's approval.</p>}
      {text && canAct && <div className="row" style={{ marginTop: 8 }}>
        {msg !== null && msg !== a.draft_message && <button className="btn sm" onClick={() => patch({ draft_message: msg }, 'Message saved')}>Save edits</button>}
        <button className="btn sm" onClick={() => { navigator.clipboard?.writeText(text); toast('Copied') }}><Copy size={13} />Copy</button>
        {!a.draft_approved && <button className="btn sm primary right" onClick={() => patch({ draft_message: msg ?? undefined, approve_draft: true }, 'Message approved')}><Check size={13} />Approve message</button>}
      </div>}
    </section>
    {canAct && a.status !== 'dismissed' && <section className="card" style={{ padding: 14, boxShadow: 'none' }}>
      <b>Record the outcome</b>
      <div className="grid g3" style={{ gap: 10, marginTop: 10 }}>
        <label className="field">Outcome<select className="input" value={outcome || a.outcome} onChange={e => setOutcome(e.target.value)}><option value="">–</option>
          {Object.entries(OUTCOME_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field">Value kept (EGP, optional)<input className="input" type="number" min={0} value={value || a.value_egp || ''} onChange={e => setValue(e.target.value)} /></label>
        <label className="field">Note<input className="input" value={note} onChange={e => setNote(e.target.value)} placeholder="What happened" /></label>
      </div>
      <button className="btn primary" style={{ marginTop: 10 }} disabled={!outcome} onClick={() => patch({ outcome, outcome_note: note, value_egp: value ? Number(value) : undefined }, 'Outcome recorded')}>Save outcome</button>
    </section>}
    <div><div className="seg-label" style={{ marginBottom: 6 }}>History</div>
      <div className="stack small" style={{ gap: 4 }}>{a.events.map((e: any, i: number) => <div key={i} className="row" style={{ flexWrap: 'nowrap' }}><span className="faint" style={{ width: 120 }}>{when(e.at)}</span><b>{e.user}</b><span className="muted">{e.detail}</span></div>)}</div></div>
    {a.call && <div className="row small"><Stars value={a.call.satisfaction} /><span className="muted">{a.call.summary}</span></div>}
  </div>
}
