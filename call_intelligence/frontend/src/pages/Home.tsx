import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUp, Check, ChevronRight, ClipboardCheck, Clock3, Frown, GraduationCap, History, ListTodo, Phone, SparklesFill, Tools,
  FileText, Users } from '@/components/icons'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { openAsk } from '@/components/Ask'
import { Topbar, useEnt, useScreen } from '@/components/Shell'
import { Empty, Skeleton, useToast } from '@/components/ui'

const TONE_DOT: Record<string, string> = { bad: 'var(--neg-accent)', warn: 'var(--warn-accent)', good: 'var(--pos-accent)', info: 'var(--info-accent)' }
const TONE_PILL: Record<string, string> = { bad: 'bad', warn: 'warn', good: 'good', info: 'info' }
const NEED: Record<string, [any, string, string]> = {
  callbacks: [Phone, 'var(--neg-bg)', 'var(--neg-text)'], promises: [Clock3, 'var(--warn-bg)', 'var(--warn-text)'],
  review: [ClipboardCheck, 'var(--info-bg)', 'var(--info-text)'], coaching: [GraduationCap, 'var(--brand-bg)', 'var(--brand-ink)'],
}
const SUGG_ICON: Record<string, any> = { tools: Tools, unhappy: Frown, team: Users, report: FileText }

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}
const pct = (v?: number | null) => (v == null ? '–' : `${Math.round(v * 100)}%`)

export default function Home() {
  const { ent, base, current, list } = useEnt()
  const { me } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const home = useQuery({ queryKey: ['home', ent], queryFn: () => api(`/e/${ent}/home`) })
  const ov = useQuery({ queryKey: ['overview-mini', ent], queryFn: () => api(`/e/${ent}/overview?period=30d`) })
  const sugg = useQuery({ queryKey: ['ask-sugg', ent, 'en'], queryFn: () => api(`/e/${ent}/assistant/suggestions?lang=en`), staleTime: 3e5 })
  useScreen({ page: 'home', title: 'Home' })
  const first = (me?.name ?? '').replace(/\(.*?\)/g, '').trim().split(/\s+/)[0]
  const h = home.data
  const k = ov.data?.kpis
  const prev = ov.data?.previous
  const where = current ? current.name : list.map(e => e.name).join(' and ')

  const callback = async (e: any) => {
    await api(`/e/${e.enterprise ?? ent}/actions`, { method: 'POST', json: { call_ids: [e.call_id], type: 'callback', title: `Call back: ${e.title}`.slice(0, 200), reason: e.body?.slice(0, 400) ?? '', priority: 'high' } })
    toast('Callback added to the Action Center')
    qc.invalidateQueries({ queryKey: ['home', ent] })
  }
  const openNeed = (n: any) => {
    // some not planned yet: Ask Sia proposes them; all planned: the Action Center, where they get done
    if (n.kind === 'callbacks') n.unplanned ? openAsk('Which unhappy customers have no callback yet? Propose callbacks for them.') : nav(`${base}/actions`)
    else if (n.kind === 'promises') nav(`${base}/actions?tab=promises`)
    else if (n.kind === 'review') nav(`${base}/review`)
    else if (n.kind === 'coaching') nav(`${base}/agents/${n.agent_id}`)
  }
  const chg = (cur?: number, old?: number, goodUp = true, pts = true) => {
    if (cur == null || old == null) return null
    const d = cur - old
    if (Math.abs(d) < 1e-9) return <span className="chg flat">Stable</span>
    return <span className={`chg ${(d > 0) === goodUp ? 'up' : 'down'}`}>{d > 0 ? '+' : '−'}{pts ? `${Math.abs(d * 100).toFixed(1)}pp` : Math.abs(d).toFixed(1)}</span>
  }
  let primaryUsed = false

  return <>
    <Topbar title="Home" />
    <div className="content">
      <section className="home-hero">
        <h1>{greeting()}{first ? `, ${first}` : ''}</h1>
        {h ? <div className="muted">{h.window === 'this week' ? 'This week' : 'Since yesterday'}: <b style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{h.new_calls} new call{h.new_calls === 1 ? '' : 's'}</b> analysed for {where}.
          {h.attention > 0 ? ` ${h.attention} thing${h.attention === 1 ? '' : 's'} need${h.attention === 1 ? 's' : ''} you today.` : ' Nothing urgent today.'}</div>
          : <div className="skeleton" style={{ width: 420, height: 20 }} />}
        <form className="ask-big" onSubmit={e => { e.preventDefault(); if (q.trim()) { openAsk(q.trim()); setQ('') } }}>
          <span className="spark"><SparklesFill size={19} /></span>
          <input dir="auto" value={q} onChange={e => setQ(e.target.value)} placeholder="Ask Sia about calls, customers or agents… or اسأل بالعربي" aria-label="Ask Sia" />
          <button className="go" aria-label="Ask"><ArrowUp size={18} /></button>
        </form>
        <div className="home-chips">{(sugg.data?.suggested ?? []).map((s: any) => { const I = SUGG_ICON[s.icon] ?? FileText
          return <button key={s.q} onClick={() => openAsk(s.q)} title={s.why}><I size={15} />{s.q}</button> })}</div>
      </section>

      <div className="split">
        <div className="tray"><section className="card widget">
          <div className="widget-head"><div className="widget-icon"><History size={16} /></div>
            <div><h3>{h?.window === 'this week' ? 'This week' : 'Since yesterday'}</h3><p>What changed in your calls, newest first</p></div>
            <div className="actions"><button className="btn sm ghost" onClick={() => nav(`${base}/calls`)}>All calls<ChevronRight size={16} /></button></div></div>
          {home.isLoading ? <Skeleton h={300} /> : !h?.events?.length ? <Empty icon={History} title="Quiet so far">New analysed calls show up here.</Empty> :
            <div className="timeline">{h.events.map((e: any, i: number) => {
              const isPrimary = e.primary === 'callback' && e.call_id && e.followup === 'none' && !primaryUsed
              if (isPrimary) primaryUsed = true
              return <div key={i} className="ev" style={{ ['--c' as any]: TONE_DOT[e.tone] }}>
                <div className="h"><b>{e.title}</b><span>{new Date(e.at).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' })}</span></div>
                <p dir="auto">{e.body}</p>
                <div className="acts">
                  {e.tags.map((t: string) => <span key={t} className={`pill ${TONE_PILL[e.tone]}`}>{t}</span>)}
                  {e.enterprise && ent === 'all' && <span className="pill plain">{list.find(x => x.id === e.enterprise)?.name ?? e.enterprise}</span>}
                  <span className="right" />
                  {e.kind === 'review' && <button className="btn sm" onClick={() => nav(`${base}/review`)}>Review</button>}
                  {e.kind === 'positive' && e.link && <button className="btn sm" onClick={() => nav(`/e/${e.enterprise}/calls?reason=${e.link.reason}&period=30d`)}>See the calls</button>}
                  {e.call_id && <button className="btn sm" onClick={() => nav(`/e/${e.enterprise ?? ent}/calls/${e.call_id}`)}>Open call</button>}
                  {e.primary === 'callback' && e.call_id && (e.followup === 'done' ? <span className="pill good"><Check size={13} />Called back</span>
                    : e.followup === 'planned' ? <button className="btn sm" onClick={() => nav(`${base}/actions`)}><Check size={14} />Callback planned</button>
                    : <button className={`btn sm ${isPrimary ? 'primary' : ''}`} onClick={() => callback(e)}>Plan a callback</button>)}
                </div>
              </div>
            })}</div>}
        </section></div>

        <div className="tray">
          <section className="card widget">
            <div className="widget-head"><div className="widget-icon"><ListTodo size={16} /></div><div><h3>Needs you today</h3><p>The shortest path from insight to action</p></div></div>
            {home.isLoading ? <Skeleton h={200} /> : !h?.needs?.length ? <Empty title="All clear">No callbacks, promises or reviews are waiting.</Empty> :
              <div>{h.needs.map((n: any) => { const [I, bg, fg] = NEED[n.kind]
                return <div key={n.kind} className="todo" role="button" tabIndex={0} onClick={() => openNeed(n)} onKeyDown={e => e.key === 'Enter' && openNeed(n)}>
                  <span className="ic" style={{ background: bg, color: fg }}><I size={16} /></span>
                  <span style={{ minWidth: 0 }}><b>{n.title}</b><span className="s">{n.sub}</span></span>
                  {n.count != null ? <span className="n">{n.count}</span> : <button className="btn sm">Open</button>}
                </div> })}</div>}
          </section>
          <div className="grid g3">
            <div className="card" style={{ padding: 12 }}><div className="tiny muted">Fully resolved</div><div className="row" style={{ gap: 6 }}><span style={{ font: '500 20px/28px var(--font)' }}>{pct(k?.resolved)}</span>{chg(k?.resolved, prev?.resolved)}</div></div>
            <div className="card" style={{ padding: 12 }}><div className="tiny muted">Satisfaction</div><div className="row" style={{ gap: 6 }}><span style={{ font: '500 20px/28px var(--font)' }}>{k?.satisfaction?.toFixed(1) ?? '–'}</span>{chg(k?.satisfaction, prev?.satisfaction, true, false)}</div></div>
            <div className="card" style={{ padding: 12 }}><div className="tiny muted">Ended unhappy</div><div className="row" style={{ gap: 6 }}><span style={{ font: '500 20px/28px var(--font)' }}>{pct(k?.negative)}</span>{chg(k?.negative, prev?.negative, false)}</div></div>
          </div>
          <button className="btn ghost" style={{ justifySelf: 'center' }} onClick={() => nav(`${base}/overview`)}>Open the full overview<ChevronRight size={16} /></button>
        </div>
      </div>
    </div>
  </>
}
