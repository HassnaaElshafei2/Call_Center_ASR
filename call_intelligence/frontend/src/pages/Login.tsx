import { useState } from 'react'
import { BarChart3, Loader2 } from 'lucide-react'
import { api, token } from '@/lib/api'
import { useAuth } from '@/lib/auth'

export default function Login() {
  const { setMe } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
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
      <form className="card login-card" onSubmit={submit}>
        <div className="row" style={{ gap: 12 }}>
          <span className="brand-mark" style={{ width: 44, height: 44, borderRadius: 14 }}><BarChart3 size={22} /></span>
          <div><h2 style={{ fontSize: 22, fontWeight: 800 }}>Call Intelligence</h2><span className="muted small">by Sia · every customer call, understood</span></div>
        </div>
        <p className="muted" style={{ margin: 0 }}>Transcription, analysis and follow-up for customer-service calls, in Egyptian Arabic.</p>
        <label className="field">Email<input className="input" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus /></label>
        <label className="field">Password<input className="input" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
        {err && <div className="pill bad" style={{ height: 'auto', padding: '8px 12px' }}>{err}</div>}
        <button className="btn primary" style={{ height: 42, justifyContent: 'center' }} disabled={busy}>{busy ? <Loader2 size={16} className="spin" /> : 'Sign in'}</button>
      </form>
    </div>
  )
}
