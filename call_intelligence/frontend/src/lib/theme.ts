import { useSyncExternalStore } from 'react'
import { flushSync } from 'react-dom'

export type Theme = 'light' | 'dark'
const KEY = 'sia-theme'
const listeners = new Set<() => void>()
let current: Theme = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'

export const useTheme = () => useSyncExternalStore(fn => (listeners.add(fn), () => listeners.delete(fn)), () => current)

/** Switch theme inside a View Transition (a circle from the click point), as Sia Prime does. */
export function setTheme(next: Theme, from?: { x: number; y: number }) {
  const apply = () => {
    current = next
    document.documentElement.dataset.theme = next
    try { localStorage.setItem(KEY, next) } catch { /* private mode */ }
    listeners.forEach(fn => fn())
  }
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
  const doc = document as Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } }
  if (!doc.startViewTransition || reduce) return apply()
  const t = doc.startViewTransition(() => flushSync(apply))
  const x = from?.x ?? innerWidth / 2, y = from?.y ?? innerHeight / 2
  const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))
  t.ready.then(() => document.documentElement.animate(
    { clipPath: [`circle(0 at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
    { duration: 500, easing: 'cubic-bezier(.22,1,.36,1)', pseudoElement: '::view-transition-new(root)' })).catch(() => {})
}

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
