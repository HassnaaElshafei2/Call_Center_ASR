import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ArrowDownRight, ArrowUpRight, Maximize2, X } from 'lucide-react'

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

export function Kpi({ icon: I, label, value, foot, bar, tint = 'var(--brand-soft)', ink = 'var(--brand-text)', change, goodWhenUp = true, onClick }: {
  icon: any; label: string; value: ReactNode; foot?: ReactNode; bar?: number | null; tint?: string; ink?: string
  change?: { value: number | null; label: string }; goodWhenUp?: boolean; onClick?: () => void
}) {
  const c = change?.value
  const good = c == null ? null : (c > 0) === goodWhenUp
  return (
    <div className={`card kpi ${onClick ? 'clickable' : ''}`} style={{ ['--tint' as any]: tint, ['--tint-ink' as any]: ink }} onClick={onClick}>
      <div className="k-head"><span className="k-icon"><I size={15} /></span>{label}</div>
      <div className="k-value num">{value}</div>
      {bar != null && <div className="k-bar"><span style={{ width: `${Math.max(2, Math.min(100, bar * 100))}%` }} /></div>}
      <div className="k-foot">
        {c != null && Math.abs(c) > 1e-9 && <span className={good ? 'up' : 'down'} style={{ display: 'inline-flex', alignItems: 'center', gap: 2, fontWeight: 600 }}>
          {c > 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{change!.label}</span>}
        <span>{foot}</span>
      </div>
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
          {(r.parts ?? [{ v: r.value, color: 'var(--brand)' }]).map((p, i) =>
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
