import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, BadgeCheck, Check, CheckCircle2, ClipboardCheck, Edit3, Eye, FileAudio, Flag, Gauge, Handshake,
  Lightbulb, ListTodo, Loader2, MessageSquareQuote, Pause, Play, Repeat2, RotateCw, ShieldAlert, Smile, Sparkles, Target, UserRound, X } from 'lucide-react'
import { api } from '@/lib/api'
import { can, useAuth } from '@/lib/auth'
import { dur, pct, title, when } from '@/lib/format'
import { ACTION_LABEL, MOODS, MoodBadge, PRIORITY_TONE, RESOLUTION, ResolutionBadge, RiskBadge, Stars } from '@/components/labels'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { Empty, Modal, Skeleton, useToast, Widget } from '@/components/ui'
import { ActionEditor } from './Actions'

const MOMENT_COLOR: Record<string, string> = {
  problem_stated: 'var(--c5)', frustration: 'var(--bad)', escalation_request: 'var(--bad)', complaint: 'var(--bad)', hold: 'var(--c7)',
  solution_offered: 'var(--c1)', resolution: 'var(--good)', promise: 'var(--gold)', gratitude: 'var(--good)', upsell: 'var(--c6)',
  compliance_issue: 'var(--bad)', confusion: 'var(--c4)',
}

export default function CallDetail() {
  const { id } = useParams()
  const { ent, base, meta } = useEnt()
  const { me } = useAuth()
  const qc = useQueryClient()
  const nav = useNavigate()
  const toast = useToast()
  const { data: c, isLoading } = useQuery({
    queryKey: ['call', ent, id], queryFn: () => api(`/e/${ent}/calls/${id}`),
    refetchInterval: q => (['done', 'failed', 'waiting_asr'].includes((q.state.data as any)?.status) ? false : 4000),
  })
  const audio = useRef<HTMLAudioElement>(null)
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [flash, setFlash] = useState<number | null>(null)
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [actionOpen, setActionOpen] = useState<string | null>(null)
  const turnRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const a = c?.analysis
  useScreen(c ? { page: 'call detail', call_id: c.id, title: `Call with ${c.customer?.name || 'a customer'} (${c.started_at?.slice(0, 10)})`,
    summary: c.summary, resolution: c.resolution, satisfaction: c.satisfaction } : { page: 'call detail' })

  const audioUrl = c?.has_audio ? `/api/e/${ent}/calls/${c.id}/audio` : null
  const durS = c?.duration_s || (c?.turns?.length ? c.turns[c.turns.length - 1].end : 0) || 1
  const current = useMemo(() => c?.turns?.find((x: any) => t >= x.start && t < x.end)?.idx, [c, t])
  useEffect(() => { if (playing && current != null) turnRefs.current[current]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [current, playing])

  const jump = (idx: number) => {
    const turn = c.turns.find((x: any) => x.idx === idx)
    if (!turn) return
    turnRefs.current[idx]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    setFlash(idx); setTimeout(() => setFlash(null), 1600)
    if (audio.current && audioUrl) { audio.current.currentTime = turn.start; setT(turn.start) }
  }
  const toggle = () => { if (!audio.current) return; if (playing) audio.current.pause(); else audio.current.play() }
  const refresh = () => qc.invalidateQueries({ queryKey: ['call', ent, id] })
  const saveTurn = async (idx: number) => {
    await api(`/e/${ent}/calls/${id}/turns/${idx}`, { method: 'PATCH', json: { text: draft } })
    setEditing(null); toast('Transcript corrected: kept as training data'); refresh()
  }
  if (isLoading || !c) return <><Topbar title="Call" /><div className="content"><Skeleton h={500} /></div></>
  const canReview = can(me, 'review', c.enterprise), canAct = can(me, 'act', c.enterprise)
  const catName = (code: string) => (meta?.categories || []).find((x: any) => x.code === code && x.enterprise === c.enterprise)?.name || title(code)
  const kpiName = (code: string) => (meta?.kpis || []).find((x: any) => x.code === code && x.enterprise === c.enterprise)?.name || title(code)

  return (
    <>
      <Topbar title={c.customer?.name ? `Call with ${c.customer.name}` : 'Call'} crumb={<Link to={`${base}/calls`}>Calls</Link>}
        actions={canReview && <button className="btn" onClick={async () => { await api(`/e/${ent}/calls/${c.id}/reanalyze`, { method: 'POST' }); toast('Analysis queued again'); refresh() }}><RotateCw size={15} />Re-analyse</button>} />
      <div className="content">
        <div className="card widget" style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 18 }}>
          <Meta label="When" value={when(c.started_at)} /><Meta label="Length" value={dur(c.duration_s)} />
          <Meta label="Agent" value={c.agent ? <Link to={`${base}/agents/${c.agent.id}`} style={{ color: 'var(--brand-text)' }}>{c.agent.name}</Link> : '–'} />
          <Meta label="Reason" value={c.reason ? catName(c.reason) : '–'} />
          <Meta label="Outcome" value={<ResolutionBadge value={c.resolution} />} /><Meta label="Predicted satisfaction" value={<Stars value={c.satisfaction} />} />
          {c.qa_score != null && <Meta label="QA score" value={<b className="num">{c.qa_score}{c.critical_fail && <span className="pill bad" style={{ marginLeft: 6 }}>critical miss</span>}</b>} />}
          <div className="row right">{c.repeat_of && <span className="pill info"><Repeat2 size={12} />Repeat call</span>}<RiskBadge value={c.churn_risk} />
            {c.compliance_issue && <span className="pill bad"><ShieldAlert size={12} />Compliance</span>}{c.needs_review && <span className="pill warn"><Flag size={12} />Needs review</span>}</div>
        </div>

        {c.status !== 'done' && <div className="card widget" style={{ flexDirection: 'row', alignItems: 'center' }}>
          {c.status === 'failed' ? <AlertTriangle className="down" /> : c.status === 'waiting_asr' ? <FileAudio /> : <Loader2 className="spin" />}
          <div><b>{({ queued: 'Queued', waiting_asr: 'Waiting for the transcription service', transcribing: 'Transcribing', analyzing: 'Analysing', failed: 'Processing failed' } as any)[c.status]}</b>
            <div className="small muted">{c.status_detail}</div></div></div>}

        <div className="split">
          <div className="stack" style={{ gap: 18 }}>
            <section className="card player">
              <div className="row">
                <button className="btn icon primary" disabled={!audioUrl} onClick={toggle} aria-label={playing ? 'Pause' : 'Play'}>{playing ? <Pause size={16} /> : <Play size={16} />}</button>
                <span className="num small">{dur(t)} / {dur(durS)}</span>
                <span className="legend right"><span><span className="dot" style={{ background: 'var(--c1)' }} />Agent</span><span><span className="dot" style={{ background: 'var(--c3)' }} />Customer</span>
                  {!audioUrl && <span className="faint">No recording: transcript only</span>}</span>
              </div>
              <div className="lanes" onClick={e => { const r = (e.currentTarget as HTMLDivElement).getBoundingClientRect(); const s = ((e.clientX - r.left) / r.width) * durS
                if (audio.current && audioUrl) audio.current.currentTime = s; setT(s); const turn = c.turns.find((x: any) => s >= x.start && s < x.end); if (turn) jump(turn.idx) }}>
                {(['agent', 'customer'] as const).map(sp => <div key={sp} className={`lane ${sp}`}>{c.turns.filter((x: any) => x.speaker === sp || (sp === 'agent' && x.speaker === 'ivr')).map((x: any) =>
                  <span key={x.idx} className={`seg ${x.speaker}`} style={{ left: `${(100 * x.start) / durS}%`, width: `${Math.max(0.3, (100 * (x.end - x.start)) / durS)}%` }} />)}</div>)}
                {(a?.moments || []).map((m: any, i: number) => { const turn = c.turns.find((x: any) => x.idx === m.turn); return turn ? <span key={i} className="moment-pin" title={`${title(m.type)}: ${m.note}`}
                  style={{ left: `${(100 * turn.start) / durS}%`, background: MOMENT_COLOR[m.type] || 'var(--brand)' }} /> : null })}
                <div className="playhead" style={{ left: `${(100 * t) / durS}%` }} />
              </div>
              {audioUrl && <audio ref={audio} src={audioUrl} preload="metadata" onTimeUpdate={e => setT(e.currentTarget.currentTime)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} />}
            </section>

            <Widget icon={MessageSquareQuote} title="Transcript" sub={`${c.turns.length} turns · Egyptian Arabic · ${transcribedBy(c.asr_model)}`}>
              {!c.turns.length ? <Empty title="No transcript yet" /> : <div className="transcript">
                {c.turns.map((x: any) => {
                  const mood = x.mood && MOODS[x.mood]
                  return <div key={x.idx} ref={el => { turnRefs.current[x.idx] = el }} className={`turn ${current === x.idx ? 'now' : ''} ${flash === x.idx ? 'flash' : ''}`}
                    onClick={() => editing !== x.idx && jump(x.idx)}>
                    <div className={`who ${x.speaker}`}>{x.speaker}<span className="faint num" style={{ fontWeight: 500 }}>{dur(x.start)}</span>
                      {mood && x.speaker === 'customer' && <span title={`Customer mood: ${mood.label}`}><mood.icon size={14} color={`var(--${mood.tone === 'good' ? 'good' : mood.tone === 'bad' ? 'bad' : mood.tone === 'warn' ? 'gold' : 'info'})`} /></span>}</div>
                    <div>
                      {editing === x.idx ? <div className="stack" onClick={e => e.stopPropagation()}>
                        <textarea className="input bubble-ar" rows={3} value={draft} onChange={e => setDraft(e.target.value)} />
                        <div className="row"><button className="btn sm primary" onClick={() => saveTurn(x.idx)}><Check size={13} />Save correction</button><button className="btn sm" onClick={() => setEditing(null)}>Cancel</button></div>
                      </div> : <div className="text">{x.text}</div>}
                      <div className="meta">{x.edited && <span className="pill plain">corrected</span>}
                        {x.confidence != null && x.confidence < 0.6 && <span className="pill warn">low confidence</span>}
                        {canReview && editing !== x.idx && <button className="btn sm ghost icon" title="Correct this line" onClick={e => { e.stopPropagation(); setEditing(x.idx); setDraft(x.text) }}><Edit3 size={13} /></button>}</div>
                    </div>
                  </div>
                })}
              </div>}
            </Widget>
          </div>

          <div className="stack" style={{ gap: 18 }}>
            {a ? <>
              <Widget icon={Sparkles} title="Summary" sub={`Analysed by ${c.analysis_meta?.model}`}>
                <p style={{ margin: 0 }}>{c.summary}</p>
                {c.summary_ar && <p className="bubble-ar muted" style={{ margin: 0 }}>{c.summary_ar}</p>}
              </Widget>
              <div className="label-card" style={{ background: 'var(--panel)' }}>
                <div className="ico" style={{ background: `color-mix(in srgb, ${RESOLUTION[c.resolution]?.color} 15%, transparent)`, color: RESOLUTION[c.resolution]?.color }}><CheckCircle2 size={20} /></div>
                <div><div className="row"><b>Was the problem solved?</b><span className="right"><ResolutionBadge value={c.resolution} /></span></div>
                  <p className="small" style={{ margin: '4px 0 0' }}>{a.resolution.explanation}</p>
                  {a.resolution.evidence_turns.slice(0, 2).map((n: number) => <Evidence key={n} c={c} n={n} onJump={jump} />)}</div>
              </div>
              <div className="label-card" style={{ background: 'var(--panel)' }}>
                <div className="ico" style={{ background: '#f7ead0', color: 'var(--gold-text)' }}><Smile size={20} /></div>
                <div><div className="row"><b>Customer satisfaction</b><span className="right"><Stars value={c.satisfaction} /></span></div>
                  <ul className="small" style={{ margin: '4px 0 0', paddingLeft: 18 }}>{a.satisfaction.signals.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
                  <div className="mood-line" style={{ marginTop: 8 }}><span className="tiny muted">Mood</span>
                    {['mood_start', 'mood_middle', 'mood_end'].map((k, i) => <span key={k} className="row" style={{ gap: 6 }}>{i > 0 && <ArrowRight size={13} className="faint" />}<MoodBadge value={a.sentiment[k]} /></span>)}</div>
                  <div className="tiny faint" style={{ marginTop: 6 }}>Predicted from the conversation, not a survey.</div></div>
              </div>
              <CustomerCard c={c} ent={ent} base={base} canAct={canAct} onChange={refresh} />
              {canReview && <ReviewCard c={c} ent={ent} cats={(meta?.categories || []).filter((x: any) => x.enterprise === c.enterprise)} onDone={refresh} />}
              <Widget icon={ListTodo} title="Recommended actions" sub="Suggested by the analysis; a person decides">
                {!c.actions.length && <span className="small muted">Nothing to follow up.</span>}
                {c.actions.map((x: any) => <div key={x.id} className="card" style={{ padding: 12, boxShadow: 'none', cursor: 'pointer' }} onClick={() => setActionOpen(x.id)}>
                  <div className="row"><span className={`pill ${PRIORITY_TONE[x.priority]}`}>{x.priority}</span><span className="pill brand">{ACTION_LABEL[x.type] || x.type}</span>
                    <span className="pill plain right">{x.status.replace('_', ' ')}</span></div>
                  <b style={{ display: 'block', marginTop: 6 }}>{x.title}</b><span className="small muted">{x.reason}</span>
                  {x.draft_message && <div className="bubble-ar small" style={{ marginTop: 6, padding: 8, borderRadius: 10, background: 'var(--panel-2)' }}>{x.draft_message}</div>}
                </div>)}
              </Widget>
            </> : <Widget icon={Sparkles} title="Analysis"><span className="muted small">The analysis appears here when the call is processed.</span></Widget>}
          </div>
        </div>

        {a && <div className="grid g3">
          <Widget icon={Target} title="Key moments" sub="Turning points; click to jump">
            {a.moments.map((m: any, i: number) => <button key={i} className="insight" style={{ border: 0, background: 'none', textAlign: 'left', gridTemplateColumns: '12px 1fr auto' }} onClick={() => jump(m.turn)}>
              <span className="dot" style={{ marginTop: 6, background: MOMENT_COLOR[m.type] }} /><p><b>{title(m.type)}</b> · <span className="muted">{m.note}</span></p><span className="tiny faint num">{dur(c.turns.find((x: any) => x.idx === m.turn)?.start)}</span></button>)}
          </Widget>
          <Widget icon={ClipboardCheck} title="QA scorecard" sub={c.qa_score != null ? `Score ${c.qa_score} of 100` : 'Not scored'}>
            {a.scorecard.map((s: any) => <div key={s.kpi} className="row small" style={{ alignItems: 'flex-start', flexWrap: 'nowrap', cursor: s.turn != null ? 'pointer' : 'default' }} onClick={() => s.turn != null && jump(s.turn)}>
              <span className={`pill ${s.result === 'pass' ? 'good' : s.result === 'fail' ? 'bad' : 'plain'}`} style={{ width: 54, justifyContent: 'center' }}>{s.result === 'pass' ? <Check size={12} /> : s.result === 'fail' ? <X size={12} /> : null}{s.result}</span>
              <span><b>{kpiName(s.kpi)}</b><span className="muted" style={{ display: 'block' }}>{s.note}</span></span></div>)}
          </Widget>
          <div className="stack" style={{ gap: 18 }}>
            <Widget icon={Gauge} title="Measured behaviour" sub="From timings, not the model">
              <Behaviour m={c.metrics} />
            </Widget>
            {(a.promises.length > 0 || a.opportunities.length > 0 || a.knowledge_gaps.length > 0 || a.risks.compliance_issues.length > 0) && <Widget icon={Lightbulb} title="Also found">
              {a.risks.compliance_issues.map((x: string, i: number) => <div key={i} className="row small" style={{ flexWrap: 'nowrap' }}><ShieldAlert size={14} className="down" />{x}</div>)}
              {c.promises.map((p: any) => <div key={p.id} className="row small" style={{ flexWrap: 'nowrap', cursor: 'pointer' }} onClick={() => p.turn != null && jump(p.turn)}><Handshake size={14} style={{ color: 'var(--gold-text)' }} />
                <span>Promise: {p.text}{p.due && <span className="muted"> · due {p.due}</span>}</span></div>)}
              {a.opportunities.map((o: any, i: number) => <div key={i} className="row small" style={{ flexWrap: 'nowrap', cursor: 'pointer' }} onClick={() => jump(o.turn)}><BadgeCheck size={14} className="up" /><span>{title(o.type)}: {o.note}</span></div>)}
              {a.knowledge_gaps.map((g: string, i: number) => <div key={i} className="row small" style={{ flexWrap: 'nowrap' }}><Lightbulb size={14} style={{ color: 'var(--info)' }} /><span>Knowledge gap: {g}</span></div>)}
            </Widget>}
          </div>
        </div>}

        {(c.repeat_of_call || c.later_calls?.length > 0) && <Widget icon={Repeat2} title="This customer's other calls">
          {[...(c.repeat_of_call ? [{ ...c.repeat_of_call, rel: 'Earlier call on the same issue' }] : []), ...c.later_calls.map((x: any) => ({ ...x, rel: 'Later call' }))].map((x: any) =>
            <div key={x.id} className="row small" style={{ cursor: 'pointer' }} onClick={() => nav(`${base}/calls/${x.id}`)}><span className="pill plain">{x.rel}</span>{when(x.started_at)}<ResolutionBadge value={x.resolution} /><span className="muted clamp1" style={{ flex: 1 }}>{x.summary}</span></div>)}
        </Widget>}
      </div>
      <Modal open={!!actionOpen} onClose={() => setActionOpen(null)} icon={ListTodo} title="Action" sub="Assign, draft the message, record the outcome">
        {actionOpen && <ActionEditor id={actionOpen} onSaved={refresh} />}
      </Modal>
    </>
  )
}

function Meta({ label, value }: { label: string; value: React.ReactNode }) {
  return <div><div className="seg-label">{label}</div><div style={{ marginTop: 3 }}>{value}</div></div>
}

function Evidence({ c, n, onJump }: { c: any; n: number; onJump: (n: number) => void }) {
  const turn = c.turns.find((x: any) => x.idx === n)
  if (!turn) return null
  return <div className="evidence" onClick={() => onJump(n)} title="Jump to this moment">«{turn.text.slice(0, 160)}{turn.text.length > 160 ? '…' : ''}» <span className="tiny faint">— {turn.speaker}, {dur(turn.start)}</span></div>
}

function Behaviour({ m }: { m: any }) {
  if (!m || !m.turns) return <span className="small muted">No timings.</span>
  const share = m.agent_talk_share
  return <div className="stack small">
    <div><div className="row"><span>Agent talk share</span><b className="right num">{pct(share)}</b></div>
      <div className="bar" style={{ marginTop: 4 }}><span style={{ width: `${(share || 0) * 100}%`, background: 'var(--c1)' }} /><span style={{ width: `${(1 - (share || 0)) * 100}%`, background: 'var(--c3)' }} /></div>
      <span className="tiny faint">{share > 0.65 ? 'The agent did most of the talking.' : share < 0.35 ? 'The customer did most of the talking.' : 'Balanced conversation.'}</span></div>
    <dl className="kv"><dt>Longest silence</dt><dd className="num">{m.longest_silence_s}s</dd><dt>Silences over 5 s</dt><dd className="num">{m.silences_over_5s}</dd>
      <dt>Talking over each other</dt><dd className="num">{m.overlaps}</dd><dt>Turns</dt><dd className="num">{m.turns}</dd>{!m.timed && <><dt /><dd className="tiny faint">Estimated from words (no audio timings)</dd></>}</dl>
  </div>
}

function CustomerCard({ c, ent, base, canAct, onChange }: any) {
  const [phone, setPhone] = useState<string | null>(null)
  const toast = useToast()
  const cu = c.customer
  if (!cu) return null
  const merge = async (into: string) => { await api(`/e/${ent}/customers/${cu.id}/merge`, { method: 'POST', json: { into } }); toast('Customers merged'); onChange() }
  return <Widget icon={UserRound} title={<Link to={`${base}/customers/${cu.id}`}>{cu.name}</Link>}
    sub={({ filename: 'Identified from the recording name (phone number)', transcript: 'Identified from a number said in the call', manual: 'Identified by a person', none: 'Name from the call; no phone number yet' } as any)[cu.identified_by]}>
    <div className="row small">
      {cu.phone ? <span className="num">{phone || cu.phone}</span> : <span className="muted">No phone number</span>}
      {cu.phone && !phone && <button className="btn sm ghost" onClick={async () => { try { const r = await api(`/e/${ent}/customers/${cu.id}/reveal-phone`, { method: 'POST' }); setPhone(r.phone) } catch (e: any) { toast(e.message) } }}><Eye size={13} />Show number</button>}
      {cu.vip && <span className="pill brand">VIP</span>}
      <Link className="btn sm right" to={`${base}/customers/${cu.id}`}>Customer page</Link>
    </div>
    {canAct && c.possible_customers?.length > 0 && <div className="stack small" style={{ gap: 6 }}>
      <span className="muted">Possibly the same customer as:</span>
      {c.possible_customers.map((p: any) => <div key={p.customer_id} className="row"><b>{p.name}</b><span className="muted">{p.phone}</span>
        <button className="btn sm right" onClick={() => merge(p.customer_id)}>It's the same person</button></div>)}
    </div>}
  </Widget>
}

function ReviewCard({ c, ent, cats, onDone }: any) {
  const [res, setRes] = useState(c.resolution)
  const [satv, setSat] = useState(c.satisfaction)
  const [reason, setReason] = useState(c.reason)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const so = c.analysis_meta?.second_opinion
  const save = async () => {
    setBusy(true)
    try { await api(`/e/${ent}/calls/${c.id}/review`, { method: 'POST', json: { resolution: res, satisfaction: Number(satv), reason_code: reason } }); toast('Review saved'); onDone() }
    finally { setBusy(false) }
  }
  return <Widget icon={ClipboardCheck} title={c.needs_review ? 'Needs your review' : 'Review'} sub={c.review_reason || 'Approve or correct the labels'}
    style={c.needs_review ? { borderColor: 'var(--gold)' } : undefined}>
    {so && <div className="small" style={{ padding: 10, borderRadius: 10, background: 'var(--panel-2)' }}><b>Second opinion:</b> {so.agree ? 'agrees' : `disagrees (${title(so.resolution)}, ${so.satisfaction}/5)`}. <span className="muted">{so.why}</span></div>}
    <div className="grid g3" style={{ gap: 8 }}>
      <label className="field">Outcome<select className="input" value={res} onChange={e => setRes(e.target.value)}>{Object.entries(RESOLUTION).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}</select></label>
      <label className="field">Satisfaction<select className="input" value={satv ?? ''} onChange={e => setSat(e.target.value)}>{[1, 2, 3, 4, 5].map(i => <option key={i} value={i}>{i}</option>)}</select></label>
      <label className="field">Reason<select className="input" value={reason} onChange={e => setReason(e.target.value)}>{cats.map((x: any) => <option key={x.code} value={x.code}>{x.name}</option>)}<option value="other">Other</option></select></label>
    </div>
    <button className="btn primary" disabled={busy} onClick={save}><Check size={15} />{res === c.resolution && Number(satv) === c.satisfaction && reason === c.reason ? 'Approve the analysis' : 'Save corrections'}</button>
  </Widget>
}

function transcribedBy(model: string): string {
  if (!model) return 'imported transcript'
  if (model.startsWith('ElevenLabs')) return 'transcribed by ElevenLabs (stand-in)'
  return 'transcribed by our fine-tuned model'
}
