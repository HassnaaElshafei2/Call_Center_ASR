import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, token } from './api'

export interface Enterprise { id: string; name: string; name_ar: string; accent: string; kind: string; role: string }
export interface Me {
  id: string; email: string; name: string; superadmin: boolean
  enterprises: Enterprise[]; permissions: Record<string, string[]>
}

const Ctx = createContext<{ me: Me | null; loading: boolean; setMe: (m: Me | null) => void; logout: () => void }>(
  { me: null, loading: true, setMe: () => {}, logout: () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    if (!token.get()) { setLoading(false); return }
    api<Me>('/me').then(setMe).catch(() => token.clear()).finally(() => setLoading(false))
  }, [])
  const logout = () => { api('/auth/logout', { method: 'POST' }).catch(() => {}); token.clear(); setMe(null); location.assign('/login') }
  return <Ctx.Provider value={{ me, loading, setMe, logout }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)

/** Can the user do `what` in enterprise `ent` ("all" = in every enterprise in scope)? */
export function can(me: Me | null, what: string, ent: string): boolean {
  if (!me) return false
  if (me.superadmin) return true
  const list = me.permissions[what] || []
  return ent === 'all' ? me.enterprises.every(e => list.includes(e.id)) : list.includes(ent)
}
