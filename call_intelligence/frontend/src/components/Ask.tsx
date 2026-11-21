import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, ArrowUpRight, Check, ChevronDown, ExternalLink, FileText, Frown, Loader2, Maximize2, Plus, Send,
  SparklesFill, Tools, Users, X, Headphones, UserRound } from '@/components/icons'
import { api, stream } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { toQuery } from '@/lib/filters'
import emblemWhite from '@/assets/brand/emblem-white.svg'
import { ACTION_LABEL, MoodBadge, ResolutionBadge } from './labels'
import { useEnt, useScreenCtx } from './Shell'
import { useToast } from './ui'

// ---------------------------------------------------------------- language (EN / ع), remembered per browser
export type Lang = 'en' | 'ar'
const LANG_KEY = 'sia-ask-lang'
function savedLang(): Lang {
  try { const v = localStorage.getItem(LANG_KEY); if (v === 'ar' || v === 'en') return v } catch { /* private mode */ }
  return navigator.language?.startsWith('ar') ? 'ar' : 'en'
}

const T = {
  en: {
    title: 'Ask', sub: 'Answers from your calls, with links to each one', hello: (n: string) => `Hi ${n}, what would you like to know?`,
    helloSub: 'Every number comes from your analysed calls.', suggested: 'Suggested for you', more: 'More ideas', back: 'Back to suggestions',
    topics: { calls: 'Calls', customers: 'Customers', agents: 'Agents', reports: 'Reports' } as Record<string, string>,
    ph: 'Ask about calls, customers or agents…', phFollow: 'Ask a follow-up…', newChat: 'New chat', thinking: 'Thinking',
    readAs: 'Read as', steps: (n: number) => `${n} step${n === 1 ? '' : 's'}`, proposed: 'Proposed', notNow: 'Not now', created: 'Created',
    create: (n: number) => `Create ${n > 1 ? `${n} actions` : 'the action'}`, calls: (n: number) => `${n} call${n === 1 ? '' : 's'}`,
    nothingCreated: 'Nothing is created until you confirm.', call: 'Call', now: 'just now', full: 'Open full page', close: 'Close',
    context: 'Uses what you are looking at',
  },
  ar: {
    title: 'اسأل', sub: 'إجابات من مكالماتكم، مع رابط لكل مكالمة', hello: (n: string) => `أهلاً يا ${n}`,
    helloSub: 'كل الأرقام هنا من مكالماتكم اللي اتحللت.', suggested: 'أسئلة مقترحة', more: 'أفكار تانية', back: 'رجوع للمقترحات',
    topics: { calls: 'المكالمات', customers: 'العملاء', agents: 'الموظفين', reports: 'التقارير' } as Record<string, string>,
    ph: 'سؤال عن المكالمات أو العملاء أو الموظفين…', phFollow: 'سؤال تاني…', newChat: 'محادثة جديدة', thinking: 'بفكر',
    readAs: 'فهمت السؤال كـ', steps: (n: number) => `${n} خطوات`, proposed: 'مقترح', notNow: 'مش دلوقتي', created: 'اتعملت',
    create: (n: number) => `إنشاء ${n > 1 ? `${n} متابعات` : 'المتابعة'}`, calls: (n: number) => `${n} مكالمة`,
    nothingCreated: 'مفيش حاجة هتتعمل غير بعد التأكيد.', call: 'المكالمة', now: 'دلوقتي', full: 'فتح في صفحة كاملة', close: 'قفل',
    context: 'بيستخدم الصفحة اللي قدامك',
  },
}

/** Open the Ask Sia panel from anywhere, optionally with a question to ask right away. */
export function openAsk(q?: string) { dispatchEvent(new CustomEvent('sia-ask', { detail: { q } })) }

interface Answer { text: string; calls: any[]; links: any[]; proposals: any[]; chips: any[]; followups?: string[] }
interface Turn { role: 'user' | 'assistant'; content: string; steps?: { label: string; done: boolean }[]; chips?: string[]; answer?: Answer; error?: string }

const SUGG_ICON: Record<string, any> = { tools: Tools, unhappy: Frown, team: Users, report: FileText }
const TOPIC_ICON: Record<string, any> = { calls: Headphones, customers: UserRound, agents: Users, reports: FileText }
const TONE: Record<string, [string, string]> = {
  warn: ['var(--warn-bg)', 'var(--warn-text)'], bad: ['var(--neg-bg)', 'var(--neg-text)'], info: ['var(--info-bg)', 'var(--info-text)'],
  brand: ['var(--brand-bg)', 'var(--brand-ink)'],
}

/** The assistant's markdown-lite: paragraphs, bullets, **bold**, and [call:ID] as links to calls. */
function AnswerText({ text, calls, onCall }: { text: string; calls: any[]; onCall: (id: string) => void }) {
  const byId = Object.fromEntries((calls || []).map(c => [c.id, c]))
  const inline = (s: string): ReactNode[] => s.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[call:[0-9a-f]{32}\])/g).map((p, i) => {
    if (p.startsWith('**')) return <b key={i}>{p.slice(2, -2)}</b>
    if (p.length > 2 && p.startsWith('*') && p.endsWith('*')) return <i key={i}>{p.slice(1, -1)}</i>
    const m = p.match(/^\[call:([0-9a-f]{32})\]$/)
    if (m) {
      const c = byId[m[1]]
      return <span key={i} className="call-ref" onClick={() => onCall(m[1])} title={c?.summary}>{c ? `${c.customer || 'call'} · ${c.date?.slice(5, 10)}` : 'call'}<ArrowUpRight size={12} /></span>
    }
    return <Fragment key={i}>{p}</Fragment>
  })
  const blocks = text.split(/\n{2,}/)
  // one direction for the whole answer, from its main language (an English line may start with an Arabic name)
  const letters = text.match(/[A-Za-z\u0600-\u06FF]/g) ?? []
  const rtl = letters.filter(ch => ch >= '\u0600').length > letters.length / 2
  return <div dir={rtl ? 'rtl' : 'ltr'}>{blocks.map((b, i) => {
    const lines = b.split('\n')
    if (lines.every(l => /^\s*([-*•]|\d+[.)])\s+/.test(l) || !l.trim())) {
      return <ul key={i}>{lines.filter(l => l.trim()).map((l, j) => <li key={j} style={{ marginInlineStart: (l.match(/^\s*/)?.[0].length ?? 0) >= 2 ? 16 : 0 }}>{inline(l.replace(/^\s*([-*•]|\d+[.)])\s+/, ''))}</li>)}</ul>
    }
    return <p key={i}>{lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l.replace(/^#+\s*/, ''))}</Fragment>)}</p>
  })}</div>
}

function Steps({ steps, done, t }: { steps: { label: string; done: boolean }[]; done: boolean; t: typeof T.en }) {
  const [open, setOpen] = useState(false)
  if (!steps.length) return null
  if (done && !open) return <button className="steps" style={{ border: 0, cursor: 'pointer', flexDirection: 'row', alignItems: 'center', gap: 6, textAlign: 'start' }}
    onClick={() => setOpen(true)}><Check size={14} className="up" />{t.steps(steps.length)}: {steps.map(s => s.label).join(' · ')}<ChevronDown size={14} style={{ marginInlineStart: 'auto' }} /></button>
  return <div className="steps">{steps.map((s, j) => <span key={j} className="step">{s.done ? <Check size={14} /> : <Loader2 size={14} className="spin" />}{s.label}</span>)}</div>
}

export function AskPanel({ page = false, onClose, initial }: { page?: boolean; onClose?: () => void; initial?: { q?: string; n: number } }) {
  const { ent, base } = useEnt()
  const { me } = useAuth()
  const { screen } = useScreenCtx()
  const nav = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [lang, setLangState] = useState<Lang>(savedLang)
  const t = T[lang]
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [topic, setTopic] = useState<string | null>(null)
  const [useCtx, setUseCtx] = useState(true)
  const box = useRef<HTMLDivElement>(null)
  const abort = useRef<AbortController | null>(null)
  const sugg = useQuery({ queryKey: ['ask-sugg', ent, lang], queryFn: () => api(`/e/${ent}/assistant/suggestions?lang=${lang}`), staleTime: 3e5 })
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight, behavior: 'smooth' }) }, [turns])
  useEffect(() => () => abort.current?.abort(), [])
  useEffect(() => { if (initial?.q) send(initial.q) }, [initial?.n])          // eslint-disable-line react-hooks/exhaustive-deps
  const setLang = (l: Lang) => { setLangState(l); try { localStorage.setItem(LANG_KEY, l) } catch { /* private mode */ } }
  const first = (me?.name ?? '').replace(/\(.*?\)/g, '').trim().split(/\s+/)[0] || ''
  const ctxLabel = !page && screen ? (screen.title || screen.page) : null

  const send = async (text: string) => {
    if (!text.trim() || busy) return
    const history = [...turns, { role: 'user' as const, content: text.trim() }]
    setTurns([...history, { role: 'assistant', content: '', steps: [] }])
    setQ(''); setTopic(null); setBusy(true)
    abort.current = new AbortController()
    const patch = (fn: (x: Turn) => Turn) => setTurns(ts => ts.map((x, i) => (i === ts.length - 1 ? fn(x) : x)))
    try {
      await stream(`/e/${ent}/assistant`, {
        messages: history.map(x => ({ role: x.role, content: x.role === 'assistant' ? (x.answer?.text || x.content) : x.content })),
        screen: !page && useCtx ? screen : null, lang,
      }, ev => {
        if (ev.type === 'step') patch(x => ({ ...x, steps: [...(x.steps || []).map(s => ({ ...s, done: true })), { label: ev.label, done: false }] }))
        if (ev.type === 'chips') patch(x => ({ ...x, chips: ev.chips.map((c: any) => c.label) }))
        if (ev.type === 'answer') patch(x => ({ ...x, content: ev.text, answer: ev, steps: (x.steps || []).map(s => ({ ...s, done: true })) }))
        if (ev.type === 'error') patch(x => ({ ...x, error: ev.message }))
      }, abort.current.signal)
    } catch (e: any) {
      if (e.name !== 'AbortError') patch(x => ({ ...x, error: e.message }))
    } finally { setBusy(false) }
  }

  const openCall = (id: string) => nav(`${base}/calls/${id}`)
  const openLink = (l: any) => nav(`${l.enterprise ? `/e/${l.enterprise}` : base}/${l.page}${toQuery(l.filters || {})}`)
  const markProposal = (p: any, state: 'done' | 'dismissed') =>
    setTurns(ts => ts.map(x => x.answer ? { ...x, answer: { ...x.answer, proposals: x.answer.proposals.map((y: any) => y === p ? { ...y, [state]: true } : y) } } : x))
  const confirm = async (p: any) => {
    await api(`/e/${ent}/actions`, { method: 'POST', json: { call_ids: p.call_ids, type: p.type, title: p.title, reason: p.reason || '', priority: p.priority || 'medium' } })
    toast(`${p.call_ids.length} action${p.call_ids.length === 1 ? '' : 's'} created`)
    qc.invalidateQueries({ queryKey: ['actions'] })
    markProposal(p, 'done')
  }

  const suggested: any[] = sugg.data?.suggested ?? []
  const topics: Record<string, string[]> = sugg.data?.topics ?? {}
  return (
    <div className={`ask-panel ${page ? 'page' : ''}`} dir={lang === 'ar' ? 'rtl' : 'ltr'} role="dialog" aria-label="Ask Sia">
      <div className="ask-head">
        <span className="spark"><SparklesFill size={17} /></span>
        <div className="tt"><b>{t.title} <span className="brand-name">Sia</span></b><span className="clamp1" style={{ display: 'block' }}>{t.sub}</span></div>
        <div className="lang" role="group" aria-label="Language">
          <button className={lang === 'en' ? 'on' : ''} onClick={() => setLang('en')} aria-pressed={lang === 'en'}>EN</button>
          <button className={`ar ${lang === 'ar' ? 'on' : ''}`} onClick={() => setLang('ar')} aria-pressed={lang === 'ar'}>ع</button>
        </div>
        {turns.length > 0 && <button className="btn sm icon ghost" onClick={() => { abort.current?.abort(); setTurns([]) }} aria-label={t.newChat} title={t.newChat}><Plus size={16} /></button>}
        {!page && <button className="btn sm icon ghost" onClick={() => { onClose?.(); nav(`${base}/ask`) }} aria-label={t.full} title={t.full}><Maximize2 size={16} /></button>}
        {onClose && <button className="btn sm icon ghost" onClick={onClose} aria-label={t.close}><X size={16} /></button>}
      </div>

      <div className="ask-msgs" ref={box}>
        {!turns.length && <>
          <div className="ask-hello"><span className="spark"><SparklesFill size={28} /></span><h3>{t.hello(first)}</h3><p>{t.helloSub}</p></div>
          {!topic ? <>
            <div className="overline" style={lang === 'ar' ? { letterSpacing: 0 } : undefined}>{t.suggested}</div>
            <div className="sugg">
              {sugg.isLoading && [0, 1, 2].map(i => <div key={i} className="skeleton" style={{ height: 62 }} />)}
              {suggested.map(s => { const I = SUGG_ICON[s.icon] ?? FileText; const [bg, fg] = TONE[s.tone] ?? TONE.brand
                return <button key={s.q} className="sg" onClick={() => send(s.q)}>
                  <span className="ic" style={{ background: bg, color: fg }}><I size={16} /></span>
                  <span><b>{s.q}</b><span className="why">{s.why}</span></span><ArrowRight size={16} />
                </button> })}
            </div>
            <div className="ask-cats"><span className="lbl">{t.more}</span>
              {Object.keys(topics).map(k => { const I = TOPIC_ICON[k]; return <button key={k} className="chip round" onClick={() => setTopic(k)}>{I && <I size={14} />}{t.topics[k] ?? k}</button> })}
            </div>
          </> : <>
            <button className="btn sm ghost" style={{ alignSelf: 'flex-start' }} onClick={() => setTopic(null)}><ArrowRight size={14} className="flip" style={{ transform: lang === 'ar' ? undefined : 'scaleX(-1)' }} />{t.back}</button>
            <div className="overline" style={lang === 'ar' ? { letterSpacing: 0 } : undefined}>{t.topics[topic]}</div>
            <div className="sugg">{(topics[topic] ?? []).map(qq => <button key={qq} className="sg" style={{ gridTemplateColumns: 'minmax(0,1fr) 16px' }} onClick={() => send(qq)}>
              <b>{qq}</b><ArrowRight size={16} /></button>)}</div>
          </>}
        </>}

        {turns.map((x, i) => x.role === 'user'
          ? <div key={i} className="msg user" dir="auto">{x.content}</div>
          : <div key={i} className="msg bot">
            <div className="who"><span className="ai-avatar"><img src={emblemWhite} alt="" /></span>Sia AI<span>· {t.now}</span></div>
            <div className="stack" style={{ gap: 8 }}>
              <Steps steps={x.steps ?? []} done={!!x.answer || !!x.error} t={t} />
              {!!x.chips?.length && <div className="row" style={{ gap: 6 }}><span className="tiny faint">{t.readAs}</span>{x.chips.map(c => <span key={c} className="pill brand">{c}</span>)}</div>}
              {busy && i === turns.length - 1 && !x.answer && !x.error && !x.steps?.length && <div className="steps"><span className="step"><Loader2 size={14} className="spin" />{t.thinking}</span></div>}
              {x.answer && <div><AnswerText text={x.answer.text} calls={x.answer.calls} onCall={openCall} /></div>}
              {x.error && <div className="pill bad" style={{ height: 'auto', padding: '8px 10px', whiteSpace: 'normal' }}>{x.error}</div>}
              {!!x.answer?.calls?.length && <div className="cited">{x.answer.calls.map((c: any) =>
                <a key={c.id} onClick={() => openCall(c.id)} style={{ cursor: 'pointer' }}>
                  {c.mood_end ? <MoodBadge value={c.mood_end} /> : <ResolutionBadge value={c.resolution} />}
                  <span className="clamp1"><span dir="auto">{c.customer || 'Customer'}</span><span className="muted"> · {c.reason || c.summary}</span></span>
                  <span className="go">{t.call}<ArrowUpRight size={12} /></span></a>)}</div>}
              {x.answer?.links?.length ? <div className="row" style={{ gap: 6 }}>{x.answer.links.map((l, j) => <button key={j} className="btn sm" onClick={() => openLink(l)}><ExternalLink size={14} />{l.label}</button>)}</div> : null}
              {x.answer?.proposals?.filter((p: any) => !p.dismissed).map((p: any, j: number) => <div key={j} className="proposal">
                <div className="ph"><SparklesFill size={16} />{t.proposed}: {ACTION_LABEL[p.type] || p.type} · {t.calls(p.call_ids.length)}</div>
                <b className="small">{p.title}</b>{p.reason && <span className="small muted">{p.reason}</span>}
                <span className="tiny muted">{t.nothingCreated}</span>
                {p.done ? <span className="pill good" style={{ alignSelf: 'flex-start' }}><Check size={13} />{t.created}</span>
                  : <div className="row"><button className="btn sm primary" onClick={() => confirm(p)}>{t.create(p.call_ids.length)}</button>
                    <button className="btn sm ghost" onClick={() => markProposal(p, 'dismissed')}>{t.notNow}</button></div>}
              </div>)}
              {!busy && i === turns.length - 1 && !!x.answer?.followups?.length && <div className="row" style={{ gap: 6 }}>
                {x.answer.followups.map(f => <button key={f} className="chip round" dir="auto" onClick={() => send(f)}>{f}</button>)}</div>}
            </div>
          </div>)}
      </div>

      <form className="ask-input" onSubmit={e => { e.preventDefault(); send(q) }}>
        <textarea dir="auto" placeholder={turns.length ? t.phFollow : t.ph} value={q} onChange={e => setQ(e.target.value)} aria-label={t.ph}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(q) } }} />
        <div className="bar2">
          {ctxLabel && useCtx && <span className="ctx" title={t.context}><span className="clamp1">{ctxLabel}</span>
            <button type="button" onClick={() => setUseCtx(false)} aria-label="Don't use this page"><X size={13} /></button></span>}
          <button className="send" disabled={busy || !q.trim()} aria-label="Send">{busy ? <Loader2 size={15} className="spin" /> : <Send size={15} className={lang === 'ar' ? 'flip' : ''} />}</button>
        </div>
      </form>
    </div>
  )
}

export function AskLauncher() {
  const [open, setOpen] = useState(false)
  const [initial, setInitial] = useState<{ q?: string; n: number }>({ n: 0 })
  const onAskPage = location.pathname.endsWith('/ask')
  const mac = /Mac|iPhone|iPad/.test(navigator.platform)
  useEffect(() => {
    const onAsk = (e: Event) => { const q = (e as CustomEvent).detail?.q; setOpen(true); if (q) setInitial(x => ({ q, n: x.n + 1 })) }
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen(o => !o) } }
    addEventListener('sia-ask', onAsk); addEventListener('keydown', onKey)
    return () => { removeEventListener('sia-ask', onAsk); removeEventListener('keydown', onKey) }
  }, [])
  if (onAskPage) return null
  return <>
    {open && <AskPanel onClose={() => setOpen(false)} initial={initial} />}
    {!open && <button className="ask-fab" onClick={() => setOpen(true)} aria-label="Open Ask Sia" title="Ask Sia about your calls">
      <span className="spark"><SparklesFill size={16} /></span><span>Ask <span className="brand-name">Sia</span></span><kbd>{mac ? '⌘K' : 'Ctrl K'}</kbd>
    </button>}
  </>
}
