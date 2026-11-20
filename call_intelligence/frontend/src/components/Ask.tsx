import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, MessageCircle, Plus, Send, Sparkles, X, ExternalLink, Phone } from 'lucide-react'
import { api, stream } from '@/lib/api'
import { toQuery } from '@/lib/filters'
import { ACTION_LABEL } from './labels'
import { useEnt, useScreenCtx } from './Shell'
import { useToast } from './ui'

interface Answer { text: string; calls: any[]; links: any[]; proposals: any[]; chips: any[] }
interface Turn { role: 'user' | 'assistant'; content: string; steps?: { label: string; done: boolean }[]; chips?: string[]; answer?: Answer; error?: string }

/** Renders the assistant's markdown-lite: paragraphs, bullets, **bold**, and [call:ID] as links to calls. */
function Answer({ text, calls, onCall }: { text: string; calls: any[]; onCall: (id: string) => void }) {
  const byId = Object.fromEntries((calls || []).map(c => [c.id, c]))
  const inline = (s: string): ReactNode[] => s.split(/(\*\*[^*]+\*\*|\[call:[0-9a-f]{32}\])/g).map((p, i) => {
    if (p.startsWith('**')) return <b key={i}>{p.slice(2, -2)}</b>
    const m = p.match(/^\[call:([0-9a-f]{32})\]$/)
    if (m) {
      const c = byId[m[1]]
      return <span key={i} className="call-ref" onClick={() => onCall(m[1])} title={c?.summary}><Phone size={11} />{c ? `${c.customer || 'call'} · ${c.date?.slice(5, 10)}` : 'call'}</span>
    }
    return <Fragment key={i}>{p}</Fragment>
  })
  const blocks = text.split(/\n{2,}/)
  return <>{blocks.map((b, i) => {
    const lines = b.split('\n')
    if (lines.every(l => /^\s*([-*•]|\d+[.)])\s+/.test(l) || !l.trim())) {
      return <ul key={i}>{lines.filter(l => l.trim()).map((l, j) => <li key={j} dir="auto">{inline(l.replace(/^\s*([-*•]|\d+[.)])\s+/, ''))}</li>)}</ul>
    }
    return <p key={i} dir="auto">{lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l.replace(/^#+\s*/, ''))}</Fragment>)}</p>
  })}</>
}

export function AskPanel({ page = false, onClose }: { page?: boolean; onClose?: () => void }) {
  const { ent, base } = useEnt()
  const { screen } = useScreenCtx()
  const nav = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const abort = useRef<AbortController | null>(null)
  const sugg = useQuery({ queryKey: ['ask-sugg', ent], queryFn: () => api(`/e/${ent}/assistant/suggestions`), staleTime: 3e5 })
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight, behavior: 'smooth' }) }, [turns])
  useEffect(() => () => abort.current?.abort(), [])

  const send = async (text: string) => {
    if (!text.trim() || busy) return
    const history = [...turns, { role: 'user' as const, content: text.trim() }]
    setTurns([...history, { role: 'assistant', content: '', steps: [] }])
    setQ('')
    setBusy(true)
    abort.current = new AbortController()
    const patch = (fn: (t: Turn) => Turn) => setTurns(ts => ts.map((t, i) => (i === ts.length - 1 ? fn(t) : t)))
    try {
      await stream(`/e/${ent}/assistant`, {
        messages: history.map(t => ({ role: t.role, content: t.role === 'assistant' ? (t.answer?.text || t.content) : t.content })),
        screen: page ? null : screen,
      }, ev => {
        if (ev.type === 'step') patch(t => ({ ...t, steps: [...(t.steps || []).map(s => ({ ...s, done: true })), { label: ev.label, done: false }] }))
        if (ev.type === 'chips') patch(t => ({ ...t, chips: ev.chips.map((c: any) => c.label) }))
        if (ev.type === 'answer') patch(t => ({ ...t, content: ev.text, answer: ev, steps: (t.steps || []).map(s => ({ ...s, done: true })) }))
        if (ev.type === 'error') patch(t => ({ ...t, error: ev.message }))
      }, abort.current.signal)
    } catch (e: any) {
      if (e.name !== 'AbortError') patch(t => ({ ...t, error: e.message }))
    } finally { setBusy(false) }
  }

  const openCall = (id: string) => nav(`${base}/calls/${id}`)
  const openLink = (l: any) => {
    const target = l.enterprise ? `/e/${l.enterprise}` : base
    nav(`${target}/${l.page}${toQuery(l.filters || {})}`)
  }
  const confirm = async (p: any) => {
    await api(`/e/${ent}/actions`, { method: 'POST', json: { call_ids: p.call_ids, type: p.type, title: p.title, reason: p.reason || '', priority: p.priority || 'medium' } })
    toast(`${p.call_ids.length} action${p.call_ids.length === 1 ? '' : 's'} created`)
    qc.invalidateQueries({ queryKey: ['actions'] })
    setTurns(ts => ts.map(t => t.answer ? { ...t, answer: { ...t.answer, proposals: t.answer.proposals.map((x: any) => x === p ? { ...x, done: true } : x) } } : t))
  }

  const list = (sugg.data?.en || []).concat(sugg.data?.ar || [])
  return (
    <div className={`ask-panel ${page ? 'page card' : ''}`}>
      <div className="ask-head">
        <div className="widget-icon" style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-2))', color: '#fff' }}><Sparkles size={18} /></div>
        <div style={{ flex: 1, minWidth: 0 }}><b>Ask</b><div className="tiny muted clamp1">{screen && !page ? `Knows you're on: ${screen.title || screen.page}` : 'Questions about your calls, customers and agents'}</div></div>
        {turns.length > 0 && <button className="btn sm ghost" onClick={() => { abort.current?.abort(); setTurns([]) }}><Plus size={14} />New</button>}
        {onClose && <button className="btn icon sm ghost" onClick={onClose} aria-label="Close"><X size={16} /></button>}
      </div>
      <div className="ask-msgs" ref={box}>
        {!turns.length && <div className="stack" style={{ marginTop: 'auto' }}>
          <p className="muted small" style={{ margin: 0 }}>Answers come from your call data: every number is counted, not guessed. Ask in English or Arabic.</p>
          {list.map((s: string) => <button key={s} className="chip" dir="auto" style={{ height: 'auto', padding: '8px 12px', whiteSpace: 'normal', textAlign: 'start', justifyContent: 'flex-start' }} onClick={() => send(s)}>{s}</button>)}
        </div>}
        {turns.map((t, i) => t.role === 'user'
          ? <div key={i} className="msg user" dir="auto">{t.content}</div>
          : <div key={i} className="stack" style={{ alignSelf: 'stretch', gap: 8 }}>
            {!!t.steps?.length && <div className="steps">{t.steps.map((s, j) => <span key={j} className="step">{s.done ? <Check size={13} className="up" /> : <Loader2 size={13} className="spin" />}{s.label}</span>)}</div>}
            {!!t.chips?.length && <div className="row" style={{ gap: 6 }}><span className="tiny faint">Read as</span>{t.chips.map(c => <span key={c} className="pill brand">{c}</span>)}</div>}
            {t.answer && <div className="msg bot"><Answer text={t.answer.text} calls={t.answer.calls} onCall={openCall} /></div>}
            {t.error && <div className="msg bot" style={{ color: 'var(--bad)' }}>{t.error}</div>}
            {busy && i === turns.length - 1 && !t.answer && !t.error && !t.steps?.length && <div className="steps"><span className="step"><Loader2 size={13} className="spin" />Thinking</span></div>}
            {t.answer?.links?.length ? <div className="row" style={{ gap: 6 }}>{t.answer.links.map((l, j) => <button key={j} className="btn sm" onClick={() => openLink(l)}><ExternalLink size={13} />{l.label}</button>)}</div> : null}
            {t.answer?.proposals?.map((p: any, j: number) => <div key={j} className="proposal">
              <span className="tiny strong" style={{ color: 'var(--brand-text)' }}>PROPOSED ACTION · {ACTION_LABEL[p.type] || p.type}</span>
              <b>{p.title}</b>{p.reason && <span className="small muted">{p.reason}</span>}
              <div className="row"><span className="small">{p.call_ids.length} call{p.call_ids.length === 1 ? '' : 's'}</span>
                {p.done ? <span className="pill good right"><Check size={12} />Created</span> : <button className="btn sm primary right" onClick={() => confirm(p)}>Create {p.call_ids.length > 1 ? `${p.call_ids.length} actions` : 'action'}</button>}</div>
            </div>)}
          </div>)}
      </div>
      <form className="ask-input" onSubmit={e => { e.preventDefault(); send(q) }}>
        <textarea className="input" dir="auto" placeholder="Ask about calls, customers, agents…  اسأل بالعربي" value={q} onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(q) } }} />
        <button className="btn primary icon" style={{ height: 44, width: 44 }} disabled={busy || !q.trim()} aria-label="Send">{busy ? <Loader2 size={17} className="spin" /> : <Send size={17} />}</button>
      </form>
    </div>
  )
}

export function AskLauncher() {
  const [open, setOpen] = useState(false)
  const onAskPage = location.pathname.endsWith('/ask')
  if (onAskPage) return null
  return <>
    {open && <AskPanel onClose={() => setOpen(false)} />}
    <button className="ask-fab" onClick={() => setOpen(o => !o)} aria-label={open ? 'Close Ask' : 'Open Ask'} title="Ask about your calls">
      {open ? <X size={24} /> : <MessageCircle size={24} />}
    </button>
  </>
}
