import { useState } from 'react'
import { Loader2 } from '@/components/icons'
import logo from '@/assets/brand/logo.svg'
import logoWhite from '@/assets/brand/logo-white.svg'
import { useTheme } from '@/lib/theme'
import { api, token } from '@/lib/api'
import { useAuth } from '@/lib/auth'

export default function Login() {
  const { setMe } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const theme = useTheme()
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const r = await api<{ token: string; user: any }>('/auth/login', { method: 'POST', json: { email, password } })
      token.set(r.token); setMe(r.user)
      const next = new URLSearchParams(location.search).get('next')
      location.assign(next && next.startsWith('/') ? next : '/')
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="row" style={{ gap: 12, flexWrap: 'nowrap' }}>
          <img src={theme === 'dark' ? logoWhite : logo} alt="Sia" style={{ height: 30 }} />
          <span style={{ width: 1, height: 24, background: 'var(--border-strong)' }} />
          <span style={{ font: '600 22px/28px var(--font)' }}>Listen</span>
        </div>
        <div><h2 style={{ font: '600 28px/36px var(--font)', letterSpacing: '-.02em' }}>Sign in</h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>Every customer call, transcribed, understood and followed up, in Egyptian Arabic.</p></div>
        <label className="field">Email<input className="input" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus /></label>
        <label className="field">Password<input className="input" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
        {err && <div className="pill bad" style={{ height: 'auto', padding: '8px 12px' }}>{err}</div>}
        <button className="btn primary" disabled={busy}>{busy ? <Loader2 size={16} className="spin" /> : 'Sign in'}</button>
      </form>
    </div>
  )
}
