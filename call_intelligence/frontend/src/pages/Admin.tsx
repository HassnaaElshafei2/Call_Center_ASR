import { Fragment, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, ClipboardCheck, Lock, Cpu, FileCog, History, Plus, RotateCw, Save, Tags, Trash2, UserCog, Users } from '@/components/icons'
import { api } from '@/lib/api'
import { can, useAuth } from '@/lib/auth'
import { when } from '@/lib/format'
import { ROLE_LABEL } from '@/components/labels'
import { Topbar, useEnt } from '@/components/Shell'
import { Empty, Modal, Skeleton, useToast, Widget } from '@/components/ui'

const TABS: [string, string, any][] = [['status', 'System', Cpu], ['users', 'Users and roles', Users], ['categories', 'Call reasons', Tags],
  ['scorecard', 'QA scorecard', ClipboardCheck], ['agents', 'Agents', UserCog], ['enterprise', 'Recording names', FileCog], ['audit', 'Audit log', History]]

export default function Admin() {
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') || 'status'
  const { me } = useAuth()
  const { ent } = useEnt()
  if (me && !can(me, 'admin', ent)) return <>
    <Topbar title="Administration" crumb="Settings" />
    <div className="content"><Empty icon={Lock} title="Only administrators can open this page">Ask an administrator if you need a change to users, call reasons or the QA scorecard.</Empty></div>
  </>
  return <>
    <Topbar title="Administration" crumb="Settings" />
    <div className="content">
      <div className="tabs" style={{ alignSelf: 'flex-start', flexWrap: 'wrap' }}>{TABS.map(([k, l, I]) =>
        <button key={k} className={tab === k ? 'on' : ''} onClick={() => setSp({ tab: k })}><I size={13} style={{ verticalAlign: -2, marginRight: 4 }} />{l}</button>)}</div>
      {tab === 'status' && <Status />}{tab === 'users' && <UsersTab />}{tab === 'categories' && <Categories />}
      {tab === 'scorecard' && <ScorecardTab />}{tab === 'agents' && <AgentsTab />}{tab === 'enterprise' && <EnterpriseTab />}{tab === 'audit' && <Audit />}
    </div>
  </>
}

function Status() {
  const { ent } = useEnt()
  const toast = useToast()
  const { data, refetch } = useQuery({ queryKey: ['admin-status', ent], queryFn: () => api(`/e/${ent}/admin/status`), refetchInterval: 10_000 })
  if (!data) return <Skeleton h={300} />
  return <div className="grid g3">
    <Widget icon={Cpu} title="Language models" sub="DGX Spark gateway">
      <dl className="kv"><dt>Status</dt><dd>{data.llm.configured ? <span className="pill good">connected</span> : <span className="pill bad">LLM_API_KEY missing or invalid</span>}</dd>
        <dt>Analysis and Ask</dt><dd>{data.llm.model}</dd><dt>Second opinion</dt><dd>{data.llm.second_opinion}</dd><dt>Search</dt><dd>{data.llm.embedding}</dd></dl>
    </Widget>
    <Widget icon={Activity} title="Transcription service" sub={data.asr.provider === 'elevenlabs' ? 'ElevenLabs Scribe, a stand-in until the DGX hosts our model (synthetic calls only)' : "Mohammed's fine-tuned Cohere model + speaker separation"}>
      <dl className="kv"><dt>Status</dt><dd>{data.asr.ok ? <span className="pill good">online</span> : <span className="pill warn">not connected</span>}</dd>
        {data.asr.model && <><dt>Model</dt><dd>{data.asr.model}</dd></>}{data.asr.device && <><dt>Device</dt><dd>{data.asr.device}</dd></>}
        {!data.asr.ok && <><dt>Why</dt><dd className="small">{data.asr.reason}</dd></>}</dl>
      <button className="btn sm" onClick={async () => { const r = await api(`/e/${ent}/admin/retry-waiting`, { method: 'POST' }); toast(`${r.queued} calls queued again`); refetch() }}><RotateCw size={13} />Retry waiting and failed calls</button>
    </Widget>
    <Widget icon={History} title="Work queue">
      <dl className="kv">{Object.entries(data.jobs).map(([k, v]: any) => <Fragment key={k}><dt>{k}</dt><dd className="num">{v}</dd></Fragment>)}</dl>
      <div className="divider" /><dl className="kv">{Object.entries(data.calls).map(([k, v]: any) => <Fragment key={k}><dt>calls {k.replace('_', ' ')}</dt><dd className="num">{v}</dd></Fragment>)}</dl>
      {data.failed_jobs.length > 0 && <details><summary className="small">Recent failures</summary>{data.failed_jobs.map((j: any) => <div key={j.id} className="tiny muted">{j.kind}: {j.error}</div>)}</details>}
    </Widget>
  </div>
}

function UsersTab() {
  const { ent, list } = useEnt()
  const { me } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['admin-users', ent], queryFn: () => api(`/e/${ent}/admin/users`) })
  const { data: meta } = useQuery({ queryKey: ['meta', ent], queryFn: () => api(`/e/${ent}/meta`) })
  const [edit, setEdit] = useState<any>(null)
  const ents = ent === 'all' ? list : list.filter(e => e.id === ent)
  const save = async () => {
    try {
      await api(`/e/${ent}/admin/users${edit.id ? `?user_id=${edit.id}` : ''}`, { method: 'POST', json: { name: edit.name, email: edit.email, password: edit.password || null, active: edit.active, roles: ents.map(e => ({ enterprise: e.id, role: edit.roles[e.id]?.role || 'none', agent_id: edit.roles[e.id]?.agent_id || null })) } })
      toast('User saved'); setEdit(null); qc.invalidateQueries({ queryKey: ['admin-users'] })
    } catch (e: any) { toast(e.message) }
  }
  const start = (u?: any) => setEdit(u ? { ...u, password: '', roles: Object.fromEntries(u.roles.map((r: any) => [r.enterprise, r])) } : { name: '', email: '', password: '', active: true, roles: {} })
  return <Widget icon={Users} title="Users and roles" sub="Roles are per enterprise" actions={<button className="btn sm primary" onClick={() => start()}><Plus size={13} />Add user</button>}>
    {!data ? <Skeleton /> : <table className="table"><thead><tr><th>Name</th><th>Email</th>{ents.map(e => <th key={e.id}>{e.name}</th>)}<th>Status</th></tr></thead>
      <tbody>{data.map((u: any) => <tr key={u.id} className="click" onClick={() => start(u)}><td><b>{u.name}</b>{u.superadmin && <span className="pill brand" style={{ marginLeft: 6 }}>superadmin</span>}</td><td className="small">{u.email}</td>
        {ents.map(e => { const r = u.roles.find((x: any) => x.enterprise === e.id); return <td key={e.id}>{r ? <span className="pill plain">{ROLE_LABEL[r.role]}</span> : <span className="faint">–</span>}</td> })}
        <td>{u.active ? <span className="pill good">active</span> : <span className="pill plain">disabled</span>}</td></tr>)}</tbody></table>}
    <Modal open={!!edit} onClose={() => setEdit(null)} narrow icon={UserCog} title={edit?.id ? 'Edit user' : 'New user'}>
      {edit && <>
        <label className="field">Name<input className="input" value={edit.name} onChange={e => setEdit({ ...edit, name: e.target.value })} /></label>
        <label className="field">Email<input className="input" value={edit.email} disabled={!!edit.id} onChange={e => setEdit({ ...edit, email: e.target.value })} /></label>
        <label className="field">{edit.id ? 'New password (leave empty to keep)' : 'Password (8+ characters)'}<input className="input" type="password" value={edit.password} onChange={e => setEdit({ ...edit, password: e.target.value })} /></label>
        {ents.map(e => <div key={e.id} className="grid g2" style={{ gap: 8 }}>
          <label className="field">{e.name} role<select className="input" value={edit.roles[e.id]?.role || 'none'} onChange={x => setEdit({ ...edit, roles: { ...edit.roles, [e.id]: { ...edit.roles[e.id], role: x.target.value } } })}>
            <option value="none">No access</option>{Object.entries(ROLE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          {edit.roles[e.id]?.role === 'agent' && <label className="field">Which agent<select className="input" value={edit.roles[e.id]?.agent_id || ''} onChange={x => setEdit({ ...edit, roles: { ...edit.roles, [e.id]: { ...edit.roles[e.id], agent_id: x.target.value } } })}>
            <option value="">–</option>{(meta?.agents || []).filter((a: any) => a.enterprise === e.id).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>}
        </div>)}
        <label className="row small"><input type="checkbox" checked={edit.active} disabled={edit.id === me?.id} onChange={e => setEdit({ ...edit, active: e.target.checked })} />Active</label>
        <button className="btn primary" onClick={save}><Save size={14} />Save</button>
        <p className="tiny muted" style={{ margin: 0 }}>Managers see everything; QA can review and correct; retention can act on customers and see phone numbers; executives view; agents see only their own calls.</p>
      </>}
    </Modal>
  </Widget>
}

function Categories() {
  const { ent, list } = useEnt()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: meta } = useQuery({ queryKey: ['meta', ent], queryFn: () => api(`/e/${ent}/meta`) })
  const [edit, setEdit] = useState<any>(null)
  const ents = ent === 'all' ? list : list.filter(e => e.id === ent)
  return <div className="stack">{ents.map(e => <Widget key={e.id} icon={Tags} title={`${e.name}: call reasons`} sub="The analysis picks one per call; changes apply to calls analysed from now on"
    actions={<button className="btn sm" onClick={() => setEdit({ enterprise: e.id, code: '', name: '', name_ar: '', description: '', active: true })}><Plus size={13} />Add</button>}>
    <table className="table"><thead><tr><th>Name</th><th>Arabic</th><th>What belongs here</th><th>Code</th><th /></tr></thead>
      <tbody>{(meta?.categories || []).filter((c: any) => c.enterprise === e.id).map((c: any) => <tr key={c.code} className="click" onClick={() => setEdit({ ...c, enterprise: e.id })}>
        <td><b>{c.name}</b>{!c.active && <span className="pill plain" style={{ marginLeft: 6 }}>off</span>}</td><td className="ar">{c.name_ar}</td><td className="small muted">{c.description}</td><td className="tiny faint">{c.code}</td><td /></tr>)}</tbody></table>
  </Widget>)}
    <Modal open={!!edit} onClose={() => setEdit(null)} narrow icon={Tags} title="Call reason">
      {edit && <>
        <label className="field">Name<input className="input" value={edit.name} onChange={e => setEdit({ ...edit, name: e.target.value })} /></label>
        <label className="field">Arabic name<input className="input ar" dir="rtl" value={edit.name_ar} onChange={e => setEdit({ ...edit, name_ar: e.target.value })} /></label>
        <label className="field">What belongs here (helps the analysis)<textarea className="input" rows={2} value={edit.description} onChange={e => setEdit({ ...edit, description: e.target.value })} /></label>
        <label className="field">Code<input className="input" value={edit.code} disabled={!!(meta?.categories || []).find((c: any) => c.code === edit.code && c.enterprise === edit.enterprise)} onChange={e => setEdit({ ...edit, code: e.target.value })} placeholder="e.g. card_delivery" /></label>
        <label className="row small"><input type="checkbox" checked={edit.active} onChange={e => setEdit({ ...edit, active: e.target.checked })} />In use</label>
        <button className="btn primary" onClick={async () => { await api(`/e/${ent}/admin/categories`, { method: 'POST', json: { ...edit, code: edit.code || edit.name } }); toast('Saved'); setEdit(null); qc.invalidateQueries({ queryKey: ['meta'] }) }}><Save size={14} />Save</button>
      </>}
    </Modal></div>
}

function ScorecardTab() {
  const { ent, list } = useEnt()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['scorecards', ent], queryFn: () => api(`/e/${ent}/admin/scorecards`) })
  const ents = ent === 'all' ? list : list.filter(e => e.id === ent)
  return <div className="stack">{ents.map(e => {
    const active = (data || []).find((s: any) => s.enterprise === e.id && s.active)
    return active ? <ScorecardEditor key={e.id + active.version} ent={ent} enterprise={e} card={active} history={(data || []).filter((s: any) => s.enterprise === e.id)}
      onSaved={() => { toast('New version published'); qc.invalidateQueries({ queryKey: ['scorecards'] }); qc.invalidateQueries({ queryKey: ['meta'] }) }} /> : null
  })}</div>
}

function ScorecardEditor({ ent, enterprise, card, history, onSaved }: any) {
  const [kpis, setKpis] = useState<any[]>(card.kpis)
  useEffect(() => setKpis(card.kpis), [card])
  const upd = (i: number, k: string, v: any) => setKpis(ks => ks.map((x, j) => (j === i ? { ...x, [k]: v } : x)))
  const changed = JSON.stringify(kpis) !== JSON.stringify(card.kpis)
  return <Widget icon={ClipboardCheck} title={`${enterprise.name}: scorecard v${card.version}`} sub={`Publishing makes v${card.version + 1}; calls keep the version that scored them · ${history.length} version${history.length > 1 ? 's' : ''}`}
    actions={<><button className="btn sm" onClick={() => setKpis([...kpis, { code: '', name: '', description: '', weight: 1, critical: false }])}><Plus size={13} />Item</button>
      <button className="btn sm primary" disabled={!changed} onClick={async () => { await api(`/e/${ent}/admin/scorecards`, { method: 'POST', json: { enterprise: enterprise.id, kpis } }); onSaved() }}><Save size={13} />Publish</button></>}>
    <table className="table"><thead><tr><th>Item</th><th>What the agent should do</th><th>Weight</th><th>Critical</th><th /></tr></thead>
      <tbody>{kpis.map((k, i) => <tr key={i}>
        <td><input className="input" style={{ width: '100%' }} value={k.name} onChange={e => upd(i, 'name', e.target.value)} />{!k.code && <input className="input" style={{ width: '100%', marginTop: 4 }} placeholder="code" value={k.code} onChange={e => upd(i, 'code', e.target.value)} />}</td>
        <td><input className="input" style={{ width: '100%' }} value={k.description} onChange={e => upd(i, 'description', e.target.value)} /></td>
        <td><input className="input" style={{ width: 70 }} type="number" step={0.5} min={0} value={k.weight} onChange={e => upd(i, 'weight', Number(e.target.value))} /></td>
        <td><input type="checkbox" checked={!!k.critical} onChange={e => upd(i, 'critical', e.target.checked)} /></td>
        <td><button className="btn sm icon ghost danger" onClick={() => setKpis(kpis.filter((_, j) => j !== i))} aria-label="Remove"><Trash2 size={14} /></button></td></tr>)}</tbody></table>
  </Widget>
}

function AgentsTab() {
  const { ent, list } = useEnt()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: meta } = useQuery({ queryKey: ['meta', ent], queryFn: () => api(`/e/${ent}/meta`) })
  const [edit, setEdit] = useState<any>(null)
  const teams = (meta?.teams || [])
  return <Widget icon={UserCog} title="Agents" sub="Who takes the calls" actions={<button className="btn sm primary" onClick={() => setEdit({ enterprise: ent === 'all' ? list[0]?.id : ent, name: '', code: '', team: '', active: true })}><Plus size={13} />Add agent</button>}>
    <table className="table"><thead><tr><th>Name</th>{ent === 'all' && <th>Enterprise</th>}<th>Team</th><th>Status</th></tr></thead>
      <tbody>{(meta?.agents || []).map((a: any) => <tr key={a.id} className="click" onClick={() => setEdit({ ...a, team: teams.find((t: any) => t.id === a.team)?.name || '' })}>
        <td><b>{a.name}</b></td>{ent === 'all' && <td>{a.enterprise.toUpperCase()}</td>}<td>{teams.find((t: any) => t.id === a.team)?.name || '–'}</td><td>{a.active ? <span className="pill good">active</span> : <span className="pill plain">inactive</span>}</td></tr>)}</tbody></table>
    <Modal open={!!edit} onClose={() => setEdit(null)} narrow icon={UserCog} title={edit?.id ? 'Edit agent' : 'New agent'}>
      {edit && <>
        {ent === 'all' && !edit.id && <label className="field">Enterprise<select className="input" value={edit.enterprise} onChange={e => setEdit({ ...edit, enterprise: e.target.value })}>{list.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>}
        <label className="field">Name<input className="input" value={edit.name} onChange={e => setEdit({ ...edit, name: e.target.value })} /></label>
        <label className="field">Employee id / extension<input className="input" value={edit.code || ''} onChange={e => setEdit({ ...edit, code: e.target.value })} /></label>
        <label className="field">Team<input className="input" list="teams" value={edit.team} onChange={e => setEdit({ ...edit, team: e.target.value })} /><datalist id="teams">{teams.filter((t: any) => t.enterprise === edit.enterprise).map((t: any) => <option key={t.id} value={t.name} />)}</datalist></label>
        <label className="row small"><input type="checkbox" checked={edit.active} onChange={e => setEdit({ ...edit, active: e.target.checked })} />Active</label>
        <button className="btn primary" onClick={async () => { await api(`/e/${ent}/admin/agents${edit.id ? `?agent_id=${edit.id}` : ''}`, { method: 'POST', json: { enterprise: edit.enterprise, name: edit.name, code: edit.code || '', team: edit.team, active: edit.active } }); toast('Saved'); setEdit(null); qc.invalidateQueries({ queryKey: ['meta'] }) }}><Save size={14} />Save</button>
      </>}
    </Modal>
  </Widget>
}

function EnterpriseTab() {
  const { ent, list } = useEnt()
  const toast = useToast()
  const ents = ent === 'all' ? list : list.filter(e => e.id === ent)
  return <div className="stack">{ents.map(e => <RulesEditor key={e.id} ent={ent} e={e} onSaved={() => toast('Saved')} />)}</div>
}

function RulesEditor({ ent, e, onSaved }: any) {
  const [rules, setRules] = useState('')
  const { data } = useQuery({ queryKey: ['ent-rules', e.id], queryFn: async () => (await api(`/e/${e.id}/meta`)).enterprises[0] })
  useEffect(() => { setRules(data?.filename_rules?.[0]?.pattern || '') }, [data])
  return <Widget icon={FileCog} title={`${e.name}: customer number in the recording name`}
    sub="A regular expression with a (?P<phone>…) group. B.TECH names its recordings by the customer's number, which links every call to the right customer.">
    <div className="row"><input className="input" style={{ flex: 1, fontFamily: 'ui-monospace, monospace' }} value={rules} onChange={x => setRules(x.target.value)} placeholder="(leave empty: no number in the name)" />
      <button className="btn primary" onClick={async () => { await api(`/e/${ent}/admin/enterprise/${e.id}`, { method: 'PATCH', json: { filename_rules: rules.trim() ? [{ pattern: rules.trim() }] : [] } }); onSaved() }}><Save size={14} />Save</button></div>
  </Widget>
}

function Audit() {
  const { ent } = useEnt()
  const { data } = useQuery({ queryKey: ['audit', ent], queryFn: () => api(`/e/${ent}/admin/audit`) })
  return <Widget icon={History} title="Audit log" sub="Who saw full phone numbers, changed labels, users, scorecards or categories">
    {!data ? <Skeleton /> : <table className="table"><thead><tr><th>When</th><th>Who</th><th>What</th><th>Target</th><th>Detail</th></tr></thead>
      <tbody>{data.map((r: any, i: number) => <tr key={i}><td className="small">{when(r.at)}</td><td>{r.user}</td><td><span className="pill plain">{r.action.replace(/_/g, ' ')}</span></td><td className="tiny muted">{r.target}</td><td className="small">{r.detail}</td></tr>)}</tbody></table>}
  </Widget>
}
