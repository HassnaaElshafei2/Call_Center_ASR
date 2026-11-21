import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Check, ChevronsUpDown, ClipboardCheck, FileText, Headphones, Home, LayoutDashboard,
  ListTodo, LogOut, Menu, Moon, Search, Settings, Sparkles, Sun, Upload, Users, UserRound } from '@/components/icons'
import logo from '@/assets/brand/logo.svg'
import logoWhite from '@/assets/brand/logo-white.svg'
import { api } from '@/lib/api'
import { can, useAuth, type Enterprise } from '@/lib/auth'
import { setTheme, useTheme } from '@/lib/theme'
import { when } from '@/lib/format'
import { AskLauncher } from './Ask'
import { UploadDialog } from './UploadDialog'

// ---------------------------------------------------------------- the enterprise in the URL, and its metadata
export function useEnt() {
  const { ent = 'all' } = useParams()
  const { me } = useAuth()
  const list = me?.enterprises ?? []
  const current: Enterprise | undefined = list.find(e => e.id === ent)
  const meta = useQuery({ queryKey: ['meta', ent], queryFn: () => api(`/e/${ent}/meta`), staleTime: 60_000 })
  return { ent, current, list, meta: meta.data as any, base: `/e/${ent}` }
}

export function entLogo(e?: { id: string; name: string; accent: string }) {
  if (!e) return { bg: 'var(--action-primary)', text: 'ALL' }
  return { bg: e.accent, text: e.name.replace(/[^A-Za-z]/g, '').slice(0, 2).toUpperCase() || e.name.slice(0, 2) }
}

function EnterpriseSwitcher() {
  const { ent, current, list } = useEnt()
  const [open, setOpen] = useState(false)
  const nav = useNavigate()
  const loc = useLocation()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const f = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    addEventListener('mousedown', f)
    return () => removeEventListener('mousedown', f)
  }, [])
  const go = (id: string) => {
    setOpen(false)
    const rest = loc.pathname.split('/').slice(3).join('/') || 'home'
    const page = rest.split('/')[0]                      // detail pages go back to their list
    nav(`/e/${id}/${page}${loc.search}`)
  }
  const options = list.length > 1 ? [{ id: 'all', name: 'All enterprises', accent: '', role: '' } as any, ...list] : list
  const shown = current ? [current] : list
  return (
    <div className="ent-switch" ref={ref}>
      {open && <div className="menu up" role="menu">
        {options.map((e: any) => {
          const l = entLogo(e.id === 'all' ? undefined : e)
          return <button key={e.id} role="menuitem" onClick={() => go(e.id)}>
            {e.id === 'all' ? <span className="ent-stack">{list.map(x => { const lx = entLogo(x); return <span key={x.id} className="org" style={{ background: lx.bg }}>{lx.text}</span> })}</span>
              : <span className="org" style={{ background: l.bg }}>{l.text}</span>}
            <span style={{ flex: 1 }}>{e.name}{e.name_ar && <span className="tiny muted ar" style={{ display: 'block' }}>{e.name_ar}</span>}</span>
            {e.id === ent && <Check size={16} />}
          </button>
        })}
      </div>}
      <button className="ent-btn" onClick={() => setOpen(o => !o)} aria-haspopup="menu" aria-expanded={open}>
        <span className="ent-stack">{shown.map(x => { const l = entLogo(x); return <span key={x.id} className="org" style={{ background: l.bg }}>{l.text}</span> })}</span>
        <span style={{ minWidth: 0, flex: 1 }}>
          <b className="clamp1">{current?.name ?? 'All enterprises'}</b>
          <small className="clamp1" style={{ display: 'block' }}>{current ? current.kind : list.map(e => e.name).join(' · ')}</small>
        </span>
        <ChevronsUpDown size={16} className="muted" />
      </button>
    </div>
  )
}

function initials(name?: string) {
  return (name ?? '?').replace(/\(.*?\)/g, '').trim().split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

function UserMenu() {
  const { me, logout } = useAuth()
  const theme = useTheme()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const f = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    addEventListener('mousedown', f)
    return () => removeEventListener('mousedown', f)
  }, [])
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button className="avatar" style={{ border: 0, cursor: 'pointer', width: 28, height: 28 }} onClick={() => setOpen(o => !o)}
        aria-label="Your account" title={me?.name}>{initials(me?.name)}</button>
      {open && <div className="menu" style={{ right: 0, top: 34, width: 250 }}>
        <div style={{ padding: '6px 8px 8px' }}><b className="small" style={{ display: 'block' }}>{me?.name}</b><span className="tiny muted">{me?.email}</span></div>
        <div className="divider" />
        <button onClick={e => setTheme(theme === 'dark' ? 'light' : 'dark', { x: e.clientX, y: e.clientY })}>
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}{theme === 'dark' ? 'Light theme' : 'Dark theme'}</button>
        <button onClick={logout}><LogOut size={16} />Sign out</button>
      </div>}
    </div>
  )
}

export function Shell() {
  const { me } = useAuth()
  const { ent, base } = useEnt()
  const theme = useTheme()
  const [sideOpen, setSideOpen] = useState(false)
  const loc = useLocation()
  useEffect(() => setSideOpen(false), [loc.pathname])
  const review = useQuery({ queryKey: ['review-count', ent], queryFn: () => api(`/e/${ent}/calls?review=true&period=all&size=1`),
    enabled: can(me, 'review', ent), refetchInterval: 60_000 })
  const actions = useQuery({ queryKey: ['open-actions', ent], queryFn: () => api(`/e/${ent}/actions`),
    refetchInterval: 120_000 })
  type Item = [string, ReactNode, any, boolean?, number?, string?]
  const groups: [string, Item[]][] = [
    ['Monitor', [['home', 'Home', Home], ['overview', 'Overview', LayoutDashboard], ['calls', 'Calls', Headphones],
      ['review', 'Review queue', ClipboardCheck, can(me, 'review', ent), review.data?.total]]],
    ['Customers', [['customers', 'Customers', UserRound], ['actions', 'Action Center', ListTodo, true, actions.data?.summary?.open, 'plain']]],
    ['Team', [['agents', 'Agents and coaching', Users]]],
    ['Reports', [['brief', 'Weekly brief', FileText], ['ask', <span>Ask <span className="brand-name">Sia</span></span>, Sparkles]]],
  ]
  return (
    <ScreenProvider>
      <div className="app">
        <aside className={`side ${sideOpen ? 'open' : ''}`}>
          <div className="brand">
            <Link to={`${base}/home`} className="row" style={{ gap: 10, flex: 1, flexWrap: 'nowrap' }} aria-label="Sia Listen, home">
              <img className="logo" src={theme === 'dark' ? logoWhite : logo} alt="Sia" /><span className="sep" /><span className="product">Listen</span>
            </Link>
            <UserMenu />
          </div>
          <nav className="nav">
            {groups.map(([g, items]) => <div key={g}>
              <div className="nav-group">{g}</div>
              {items.filter(i => i[3] !== false).map(([to, label, I, , n, tone]) => (
                <NavLink key={to} to={`${base}/${to}`}><I size={18} />{label}{!!n && <span className={`count ${tone ?? ''}`}>{n}</span>}</NavLink>
              ))}
            </div>)}
          </nav>
          <div className="side-foot nav">
            {(me?.superadmin || can(me, 'admin', ent)) && <NavLink to={`${base}/admin`}><Settings size={18} />Settings</NavLink>}
            <EnterpriseSwitcher />
          </div>
        </aside>
        <main className="main">
          <button className="btn icon menu-btn" style={{ position: 'fixed', top: 20, left: 16, zIndex: 60 }} onClick={() => setSideOpen(o => !o)} aria-label="Menu"><Menu size={18} /></button>
          <Outlet />
        </main>
      </div>
      <AskLauncher />
    </ScreenProvider>
  )
}

// ---------------------------------------------------------------- page header bar
export function Topbar({ title, crumb, actions }: { title: ReactNode; crumb?: ReactNode; actions?: ReactNode }) {
  const { ent, current, base } = useEnt()
  const { me } = useAuth()
  const [q, setQ] = useState('')
  const [upload, setUpload] = useState(false)
  const nav = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) && !t.isContentEditable) { e.preventDefault(); input.current?.focus() }
    }
    addEventListener('keydown', k)
    return () => removeEventListener('keydown', k)
  }, [])
  return (
    <header className="topbar">
      <div className="title">
        <h1>{title}</h1>
        <div className="crumb">{current?.name ?? 'All enterprises'}{crumb && <> · {crumb}</>}</div>
      </div>
      <div className="spacer" />
      <form className="search" onSubmit={e => { e.preventDefault(); if (q.trim()) nav(`${base}/calls?q=${encodeURIComponent(q.trim())}&period=all`) }}>
        <Search size={16} /><input ref={input} className="input" placeholder="Search calls, customers, words" value={q} onChange={e => setQ(e.target.value)} />
        {!q && <kbd>/</kbd>}
      </form>
      {actions}
      <AlertsBell />
      {ent !== 'all' && can(me, 'upload', ent) && <button className="btn" onClick={() => setUpload(true)}><Upload size={16} />Upload calls</button>}
      <UploadDialog open={upload} onClose={() => setUpload(false)} />
    </header>
  )
}

function AlertsBell() {
  const { ent, base } = useEnt()
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()
  const ref = useRef<HTMLDivElement>(null)
  const { data } = useQuery({ queryKey: ['alerts', ent], queryFn: () => api(`/e/${ent}/alerts?status=new,seen`), refetchInterval: 60_000 })
  useEffect(() => {
    const f = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    addEventListener('mousedown', f)
    return () => removeEventListener('mousedown', f)
  }, [])
  const seen = async () => { await api(`/e/${ent}/alerts/status`, { method: 'POST', json: { status: 'seen' } }); qc.invalidateQueries({ queryKey: ['alerts', ent] }) }
  const n = data?.new ?? 0
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button className="btn icon" aria-label={`Alerts, ${n} new`} onClick={() => { setOpen(o => !o); if (!open && n) seen() }}>
        <Bell size={18} />{n > 0 && <span style={{ position: 'absolute', top: 8, right: 9, width: 8, height: 8, borderRadius: '50%', background: 'var(--neg-accent)', boxShadow: '0 0 0 2px var(--bg-primary)' }} />}
      </button>
      {open && <div className="menu" style={{ right: 0, top: 44, width: 380, maxHeight: 460, overflow: 'auto' }}>
        <div className="row" style={{ padding: '6px 10px' }}><b>Alerts</b><span className="tiny muted right">{data?.alerts?.length ?? 0}</span></div>
        {(data?.alerts ?? []).slice(0, 30).map((a: any) => (
          <button key={a.id} onClick={() => { setOpen(false); a.call_id && nav(`${base}/calls/${a.call_id}`) }} style={{ alignItems: 'flex-start' }}>
            <span className="dot" style={{ marginTop: 6, background: a.severity === 'high' ? 'var(--neg-accent)' : 'var(--warn-accent)' }} />
            <span style={{ flex: 1 }}><span className="small" style={{ display: 'block' }}>{a.title}</span>
              <span className="tiny muted">{when(a.at)} · {a.kind.replace(/_/g, ' ')}{ent === 'all' ? ` · ${a.enterprise.toUpperCase()}` : ''}</span></span>
          </button>
        ))}
        {!data?.alerts?.length && <div className="empty small">No alerts. Calls with very unhappy customers, compliance issues or churn risk appear here.</div>}
      </div>}
    </div>
  )
}

// ---------------------------------------------------------------- what's on screen (for the assistant)
const ScreenCtx = createContext<{ screen: any; setScreen: (s: any) => void }>({ screen: null, setScreen: () => {} })
function ScreenProvider({ children }: { children: ReactNode }) {
  const [screen, setScreen] = useState<any>(null)
  return <ScreenCtx.Provider value={{ screen, setScreen }}>{children}</ScreenCtx.Provider>
}
export const useScreenCtx = () => useContext(ScreenCtx)
/** Pages call this so "this call", "these calls", "this agent" in the assistant mean what's on screen. */
export function useScreen(s: any) {
  const { setScreen } = useContext(ScreenCtx)
  const key = JSON.stringify(s)
  useEffect(() => { setScreen(s) }, [key])          // eslint-disable-line react-hooks/exhaustive-deps
}
