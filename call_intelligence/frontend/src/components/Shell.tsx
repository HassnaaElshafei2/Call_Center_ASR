import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, BarChart3, Building2, Check, ChevronsUpDown, ClipboardCheck, FileText, Headphones, LayoutDashboard,
  ListTodo, LogOut, Menu, MessageCircle, Moon, Search, Settings, Sun, Upload, Users, UserRound } from 'lucide-react'
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
  if (!e) return { bg: 'linear-gradient(135deg, var(--brand), var(--brand-2))', text: 'ALL' }
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
    const rest = loc.pathname.split('/').slice(3).join('/') || 'overview'
    const page = rest.split('/')[0]                      // detail pages go back to their list
    nav(`/e/${id}/${page}${loc.search}`)
  }
  const logo = entLogo(current)
  const options = list.length > 1 ? [{ id: 'all', name: 'All enterprises', accent: '', role: '' } as any, ...list] : list
  return (
    <div className="ent-switch" ref={ref}>
      <button className="ent-btn" onClick={() => setOpen(o => !o)} aria-haspopup="menu" aria-expanded={open}>
        <span className="ent-logo" style={{ background: logo.bg }}>{logo.text}</span>
        <span style={{ minWidth: 0, flex: 1 }}>
          <b className="clamp1" style={{ display: 'block', fontSize: 13.5 }}>{current?.name ?? 'All enterprises'}</b>
          <span className="tiny muted">{current ? current.kind : `${list.length} enterprises`}</span>
        </span>
        <ChevronsUpDown size={15} className="muted" />
      </button>
      {open && <div className="menu" role="menu" style={{ top: 'calc(100% + 6px)', left: 0, right: 0 }}>
        {options.map((e: any) => {
          const l = entLogo(e.id === 'all' ? undefined : e)
          return <button key={e.id} role="menuitem" onClick={() => go(e.id)}>
            <span className="ent-logo" style={{ background: l.bg, width: 26, height: 26, fontSize: 10.5 }}>{l.text}</span>
            <span style={{ flex: 1 }}>{e.name}{e.name_ar && <span className="tiny muted ar" style={{ display: 'block' }}>{e.name_ar}</span>}</span>
            {e.id === ent && <Check size={15} />}
          </button>
        })}
      </div>}
    </div>
  )
}

function ThemeToggle() {
  const theme = useTheme()
  return <button className="btn icon" aria-label="Switch theme" title="Light / dark"
    onClick={e => setTheme(theme === 'dark' ? 'light' : 'dark', { x: e.clientX, y: e.clientY })}>
    {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
  </button>
}

export function Shell() {
  const { me, logout } = useAuth()
  const { ent, base } = useEnt()
  const [sideOpen, setSideOpen] = useState(false)
  const loc = useLocation()
  useEffect(() => setSideOpen(false), [loc.pathname])
  const review = useQuery({ queryKey: ['review-count', ent], queryFn: () => api(`/e/${ent}/calls?review=true&period=all&size=1`),
    enabled: can(me, 'review', ent), refetchInterval: 60_000 })
  const items: [string, string, any, boolean?, number?][] = [
    ['overview', 'Overview', LayoutDashboard], ['calls', 'Calls', Headphones],
    ['review', 'Review queue', ClipboardCheck, can(me, 'review', ent), review.data?.total],
    ['customers', 'Customers', UserRound], ['agents', 'Agents', Users], ['actions', 'Action Center', ListTodo],
    ['brief', 'Weekly brief', FileText], ['ask', 'Ask', MessageCircle],
  ]
  return (
    <ScreenProvider>
      <div className="app">
        <aside className={`side ${sideOpen ? 'open' : ''}`}>
          <Link to={`${base}/overview`} className="brand">
            <span className="brand-mark"><BarChart3 size={18} /></span>
            <span><b>Call Intelligence</b><small>Sia</small></span>
          </Link>
          <EnterpriseSwitcher />
          <nav className="nav stack" style={{ gap: 2, marginTop: 8 }}>
            {items.filter(i => i[3] !== false).map(([to, label, I, , n]) => (
              <NavLink key={to} to={`${base}/${to}`}><I size={17} />{label}{!!n && <span className="count">{n}</span>}</NavLink>
            ))}
            {(me?.superadmin || can(me, 'admin', ent)) && <>
              <div className="nav-group">Settings</div>
              <NavLink to={`${base}/admin`}><Settings size={17} />Administration</NavLink>
            </>}
          </nav>
          <div className="side-foot">
            <div className="row" style={{ gap: 8 }}>
              <ThemeToggle />
              <div style={{ minWidth: 0, flex: 1 }}>
                <b className="clamp1 small" style={{ display: 'block' }}>{me?.name}</b>
                <span className="tiny muted clamp1" style={{ display: 'block' }}>{me?.email}</span>
              </div>
              <button className="btn icon ghost" onClick={logout} aria-label="Sign out" title="Sign out"><LogOut size={16} /></button>
            </div>
          </div>
        </aside>
        <main className="main">
          <button className="btn icon menu-btn" style={{ position: 'fixed', top: 14, left: 12, zIndex: 60 }} onClick={() => setSideOpen(o => !o)} aria-label="Menu"><Menu size={17} /></button>
          <Outlet />
        </main>
      </div>
      <AskLauncher />
    </ScreenProvider>
  )
}

// ---------------------------------------------------------------- page top bar
export function Topbar({ title, crumb, actions }: { title: ReactNode; crumb?: ReactNode; actions?: ReactNode }) {
  const { ent, current, base } = useEnt()
  const { me } = useAuth()
  const [q, setQ] = useState('')
  const [upload, setUpload] = useState(false)
  const nav = useNavigate()
  return (
    <header className="topbar">
      <div className="title" style={{ paddingLeft: 0 }}>
        <div className="crumb"><Building2 size={12} />{current?.name ?? 'All enterprises'}{crumb && <> / {crumb}</>}</div>
        <h1>{title}</h1>
      </div>
      <div className="spacer" />
      <form className="search" onSubmit={e => { e.preventDefault(); if (q.trim()) nav(`${base}/calls?q=${encodeURIComponent(q.trim())}&period=all`) }}>
        <Search size={15} /><input className="input" placeholder="Search calls, words, customers…" value={q} onChange={e => setQ(e.target.value)} />
      </form>
      {actions}
      {ent !== 'all' && can(me, 'upload', ent) && <button className="btn primary" onClick={() => setUpload(true)}><Upload size={15} />Upload calls</button>}
      <AlertsBell />
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
        <Bell size={16} />{n > 0 && <span style={{ position: 'absolute', top: -3, right: -3, minWidth: 18, height: 18, borderRadius: 9, background: 'var(--bad)', color: '#fff', fontSize: 10.5, fontWeight: 700, display: 'grid', placeItems: 'center', padding: '0 4px' }}>{n}</span>}
      </button>
      {open && <div className="menu" style={{ right: 0, top: 44, width: 380, maxHeight: 460, overflow: 'auto' }}>
        <div className="row" style={{ padding: '6px 10px' }}><b>Alerts</b><span className="tiny muted right">{data?.alerts?.length ?? 0}</span></div>
        {(data?.alerts ?? []).slice(0, 30).map((a: any) => (
          <button key={a.id} onClick={() => { setOpen(false); a.call_id && nav(`${base}/calls/${a.call_id}`) }} style={{ alignItems: 'flex-start' }}>
            <span className="dot" style={{ marginTop: 6, background: a.severity === 'high' ? 'var(--bad)' : 'var(--gold)' }} />
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
