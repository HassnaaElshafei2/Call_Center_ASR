import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Crown, Eye, Handshake, History, ListTodo, Phone, Plus, Smile, UserRound } from '@/components/icons'
import { api } from '@/lib/api'
import { can, useAuth } from '@/lib/auth'
import { dur, when } from '@/lib/format'
import { Chart, axis } from '@/components/Chart'
import { ACTION_LABEL, PRIORITY_TONE, ResolutionBadge, Stars } from '@/components/labels'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { Modal, Skeleton, useToast, Widget } from '@/components/ui'
import { ActionEditor } from './Actions'

export default function CustomerDetail() {
  const { id } = useParams()
  const { ent, base } = useEnt()
  const { me } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [phone, setPhone] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [newAction, setNewAction] = useState(false)
  const { data: c, refetch } = useQuery({ queryKey: ['customer', ent, id], queryFn: () => api(`/e/${ent}/customers/${id}`) })
  useScreen(c ? { page: 'customer', customer_id: c.id, title: `Customer ${c.name}`, risk: c.risk } : { page: 'customer' })
  if (!c) return <><Topbar title="Customer" /><div className="content"><Skeleton h={400} /></div></>
  const canAct = can(me, 'act', c.enterprise)
  const reveal = async () => { try { setPhone((await api(`/e/${ent}/customers/${c.id}/reveal-phone`, { method: 'POST' })).phone) } catch (e: any) { toast(e.message) } }
  return (
    <>
      <Topbar title={c.name} crumb={<Link to={`${base}/customers`}>Customers</Link>} />
      <div className="content">
        <div className="split">
          <div className="stack" style={{ gap: 18 }}>
            <Widget icon={History} title="Calls" sub={`${c.calls.length} call${c.calls.length === 1 ? '' : 's'} with this customer`}>
              <table className="table"><thead><tr><th>When</th><th>Agent</th><th style={{ width: '45%' }}>What happened</th><th>Outcome</th><th>Satisfaction</th><th>Length</th></tr></thead>
                <tbody>{c.calls.map((x: any) => <tr key={x.id} className="click" onClick={() => nav(`${base}/calls/${x.id}`)}>
                  <td className="small">{when(x.started_at)}</td><td className="small">{x.agent?.name || '–'}</td><td className="small"><div className="clamp">{x.summary || x.status}</div></td>
                  <td><ResolutionBadge value={x.resolution} /></td><td><Stars value={x.satisfaction} /></td><td className="num small">{dur(x.duration_s)}</td></tr>)}</tbody></table>
            </Widget>
            {c.satisfaction_trend.length > 1 && <Widget icon={Smile} title="Satisfaction over time" sub="Predicted, per call">
              <Chart height={200} onClick={(p: any) => nav(`${base}/calls/${c.satisfaction_trend[p.dataIndex].call_id}`)} option={t => ({
                grid: { left: 30, right: 16, top: 16, bottom: 24 }, xAxis: { type: 'category', data: c.satisfaction_trend.map((x: any) => x.date.slice(5, 10)), ...axis(t) },
                yAxis: { type: 'value', min: 1, max: 5, interval: 1, ...axis(t) },
                series: [{ type: 'line', data: c.satisfaction_trend.map((x: any) => x.satisfaction), symbolSize: 10, lineStyle: { width: 3 }, areaStyle: { opacity: 0.08 } }] })} />
            </Widget>}
          </div>
          <div className="stack" style={{ gap: 18 }}>
            <Widget icon={UserRound} title={c.name} sub={({ filename: 'Identified by the recording name', transcript: 'Identified by a number said in a call', none: 'Name from the call' } as any)[c.identified_by] || ''}>
              <div className="row">{c.phone ? <><Phone size={14} /><span className="num">{phone || c.phone}</span>{c.can_reveal && !phone && <button className="btn sm ghost" onClick={reveal}><Eye size={13} />Show</button>}</> : <span className="muted small">No phone number</span>}
                {canAct && <button className={`btn sm right ${c.vip ? 'primary' : ''}`} onClick={async () => { await api(`/e/${ent}/customers/${c.id}`, { method: 'PATCH', json: { vip: !c.vip } }); refetch() }}><Crown size={13} />{c.vip ? 'VIP' : 'Mark VIP'}</button>}</div>
              <div className={`label-card`} style={{ background: c.risk === 'high' ? 'var(--bad-bg)' : c.risk === 'medium' ? 'var(--warn-bg)' : 'var(--good-bg)' }}>
                <div className="ico"><AlertTriangle size={20} /></div>
                <div><b>{c.risk === 'high' ? 'At risk' : c.risk === 'medium' ? 'Worth watching' : 'No warning signs'}</b>
                  {c.risk_why.length > 0 && <ul className="small" style={{ margin: '4px 0 0', paddingLeft: 18 }}>{c.risk_why.map((w: string) => <li key={w}>{w}</li>)}</ul>}</div>
              </div>
            </Widget>
            <Widget icon={ListTodo} title="Follow-ups" actions={canAct && c.calls[0] && <button className="btn sm" onClick={() => setNewAction(true)}><Plus size={13} />New</button>}>
              {!c.actions.length && <span className="small muted">No actions yet.</span>}
              {c.actions.map((a: any) => <div key={a.id} className="row small" style={{ cursor: 'pointer' }} onClick={() => setOpen(a.id)}>
                <span className={`pill ${PRIORITY_TONE[a.priority]}`}>{ACTION_LABEL[a.type]}</span><span className="clamp1" style={{ flex: 1 }}>{a.title}</span><span className="pill plain">{a.status.replace('_', ' ')}</span></div>)}
            </Widget>
            {c.promises.length > 0 && <Widget icon={Handshake} title="Promises made">
              {c.promises.map((p: any) => <Link key={p.id} to={`${base}/calls/${p.call_id}`} className="row small"><span className={`pill ${p.status === 'open' ? 'warn' : p.status === 'kept' ? 'good' : 'bad'}`}>{p.status}</span>
                <span className="bubble-ar" style={{ flex: 1 }}>{p.text}</span><span className="faint">{p.due}</span></Link>)}
            </Widget>}
          </div>
        </div>
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} icon={ListTodo} title="Action">{open && <ActionEditor id={open} onSaved={refetch} />}</Modal>
      <NewAction open={newAction} onClose={() => setNewAction(false)} callId={c.calls[0]?.id} ent={ent} onDone={() => { refetch(); qc.invalidateQueries({ queryKey: ['actions'] }) }} />
    </>
  )
}

export function NewAction({ open, onClose, callId, ent, onDone }: { open: boolean; onClose: () => void; callId?: string; ent: string; onDone: () => void }) {
  const [type, setType] = useState('callback')
  const [titleV, setTitle] = useState('')
  const [priority, setPriority] = useState('medium')
  const toast = useToast()
  return <Modal open={open} onClose={onClose} narrow icon={Plus} title="New follow-up">
    <label className="field">Type<select className="input" value={type} onChange={e => setType(e.target.value)}>{Object.entries(ACTION_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
    <label className="field">What to do<input className="input" value={titleV} onChange={e => setTitle(e.target.value)} placeholder="e.g. Call back about the refund" /></label>
    <label className="field">Priority<select className="input" value={priority} onChange={e => setPriority(e.target.value)}><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
    <button className="btn primary" disabled={!titleV.trim()} onClick={async () => {
      await api(`/e/${ent}/actions`, { method: 'POST', json: { call_ids: callId ? [callId] : [], type, title: titleV, priority } })
      toast('Action created'); onClose(); onDone()
    }}>Create</button>
  </Modal>
}
