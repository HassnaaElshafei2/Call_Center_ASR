import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Maximize2, X } from '@/components/icons'

export function Widget({ icon: I, title, sub, actions, children, className = '', onExpand, style }: {
  icon?: any; title: ReactNode; sub?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string
  onExpand?: () => void; style?: React.CSSProperties
}) {
  return (
    <section className={`card widget ${className}`} style={style}>
      <div className="widget-head">
        {I && <div className="widget-icon"><I size={18} /></div>}
        <div style={{ minWidth: 0 }}><h3>{title}</h3>{sub && <p>{sub}</p>}</div>
        <div className="actions">{actions}{onExpand && <button className="btn sm icon ghost" onClick={onExpand} aria-label="Open larger"><Maximize2 size={15} /></button>}</div>
      </div>
      {children}
    </section>
  )
}

export function Modal({ open, onClose, icon: I, title, sub, children, narrow, actions }: {
  open: boolean; onClose: () => void; icon?: any; title: ReactNode; sub?: ReactNode; children: ReactNode; narrow?: boolean; actions?: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    addEventListener('keydown', k)
    document.body.style.overflow = 'hidden'
    return () => { removeEventListener('keydown', k); document.body.style.overflow = '' }
  }, [open, onClose])
  if (!open) return null
  return createPortal(
    <div className="scrim" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${narrow ? 'narrow' : ''}`} role="dialog" aria-modal="true">
        <div className="modal-head">
          {I && <div className="widget-icon"><I size={22} /></div>}
          <div style={{ minWidth: 0 }}><h2>{title}</h2>{sub && <p>{sub}</p>}</div>
          <div className="row right">{actions}<button className="btn icon" onClick={onClose} aria-label="Close"><X size={18} /></button></div>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>, document.body)
}

/** KPI card (guidelines): label with icon, value with a change chip, optional mini bars (last periods; the newest in indigo). */
export function Kpi({ icon: I, label, value, suffix, foot, bar, change, goodWhenUp = true, mini, onClick }: {
  icon: any; label: string; value: ReactNode; suffix?: ReactNode; foot?: ReactNode; bar?: number | null
  tint?: string; ink?: string; change?: { value: number | null; label: string }; goodWhenUp?: boolean; mini?: number[]; onClick?: () => void
}) {
  const c = change?.value
  const tone = c == null ? null : Math.abs(c) < 1e-9 ? 'flat' : (c > 0) === goodWhenUp ? 'up' : 'down'
  const max = Math.max(1e-9, ...(mini ?? [0]))
  return (
    <div className={`card kpi ${onClick ? 'clickable' : ''}`} onClick={onClick}>
      <div className="k-head"><I size={16} />{label}</div>
      <div className="k-value">{value}{suffix && <small>{suffix}</small>}
        {tone && <span className={`chg ${tone}`}>{tone === 'flat' ? 'Stable' : change!.label}</span>}</div>
      {mini && mini.length > 1 && <svg className="k-mini" width={mini.length * 12} height="32" aria-hidden>
        {mini.map((v, i) => { const h = Math.max(2, (v / max) * 30); return <rect key={i} x={i * 12} y={32 - h} width="8" height={h} rx="2"
          fill={i >= mini.length - 1 ? 'var(--bar-hi)' : 'var(--bar)'} /> })}</svg>}
      {bar != null && !mini && <div className="bar" style={{ height: 4, marginTop: 4 }}><span style={{ width: `${Math.max(2, Math.min(100, bar * 100))}%`, background: bar > .85 ? 'var(--pos-accent)' : 'var(--neutral-accent)' }} /></div>}
      {foot && <div className="k-foot">{foot}</div>}
    </div>
  )
}

export function Empty({ icon: I, title, children }: { icon?: any; title: string; children?: ReactNode }) {
  return <div className="empty">{I && <I size={28} />}<b style={{ color: 'var(--ink)' }}>{title}</b>{children}</div>
}

export function Skeleton({ h = 120 }: { h?: number }) {
  return <div className="skeleton" style={{ height: h }} />
}

export function BarList({ rows, onClick, total }: {
  rows: { key: string; label: ReactNode; value: number; parts?: { v: number; color: string; title?: string }[]; right?: ReactNode }[]
  onClick?: (key: string) => void; total?: number
}) {
  const max = total ?? Math.max(1, ...rows.map(r => r.value))
  return <div className="stack" style={{ gap: 2 }}>
    {rows.map(r => (
      <div key={r.key} className={`bar-row ${onClick ? 'click' : ''}`} onClick={() => onClick?.(r.key)}>
        <span className="clamp1" style={{ fontWeight: 500 }}>{r.label}</span>
        <span className="num small" style={{ fontWeight: 600 }}>{r.right ?? r.value}</span>
        <div className="bar">
          {(r.parts ?? [{ v: r.value, color: 'var(--chart-1)' }]).map((p, i) =>
            <span key={i} title={p.title} style={{ width: `${(100 * p.v) / max}%`, background: p.color }} />)}
        </div>
      </div>
    ))}
  </div>
}

// ---------------------------------------------------------------- toasts
const ToastCtx = createContext<(msg: string) => void>(() => {})
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<{ id: number; msg: string }[]>([])
  const push = useCallback((msg: string) => {
    const id = Date.now() + Math.random()
    setItems(x => [...x, { id, msg }])
    setTimeout(() => setItems(x => x.filter(i => i.id !== id)), 3200)
  }, [])
  return <ToastCtx.Provider value={push}>{children}
    {createPortal(<div className="toast-wrap" aria-live="polite">{items.map(i => <div key={i.id} className="toast">{i.msg}</div>)}</div>, document.body)}
  </ToastCtx.Provider>
}
export const useToast = () => useContext(ToastCtx)

/** Bold (**x**) and line breaks in computed insight sentences. */
export function Rich({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return <>{parts.map((p, i) => p.startsWith('**') ? <b key={i}>{p.slice(2, -2)}</b> : <span key={i}>{p}</span>)}</>
}
