import { AlertTriangle, CheckCircle2, CircleDashed, Frown, Meh, Smile, Star, XCircle, Angry, HelpCircle, ShieldAlert } from '@/components/icons'

// Every status shows an icon/shape as well as a colour.
export const RESOLUTION: Record<string, { label: string; tone: string; icon: any; color: string }> = {
  resolved: { label: 'Resolved', tone: 'good', icon: CheckCircle2, color: 'var(--good)' },
  partly_resolved: { label: 'Partly resolved', tone: 'warn', icon: CircleDashed, color: 'var(--gold)' },
  not_resolved: { label: 'Not resolved', tone: 'bad', icon: XCircle, color: 'var(--bad)' },
}

export const MOODS: Record<string, { label: string; tone: string; icon: any; score: number }> = {
  happy: { label: 'Happy', tone: 'good', icon: Smile, score: 2 },
  calm: { label: 'Calm', tone: 'good', icon: Smile, score: 1 },
  confused: { label: 'Confused', tone: 'info', icon: HelpCircle, score: 0 },
  worried: { label: 'Worried', tone: 'warn', icon: Meh, score: -0.5 },
  frustrated: { label: 'Frustrated', tone: 'bad', icon: Frown, score: -1.5 },
  angry: { label: 'Angry', tone: 'bad', icon: Angry, score: -2 },
}

export function ResolutionBadge({ value }: { value?: string }) {
  const r = value ? RESOLUTION[value] : null
  if (!r) return <span className="pill plain">Not analysed</span>
  const I = r.icon
  return <span className={`pill ${r.tone}`}><I size={13} />{r.label}</span>
}

export function MoodBadge({ value }: { value?: string }) {
  const m = value ? MOODS[value] : null
  if (!m) return null
  const I = m.icon
  return <span className={`pill ${m.tone}`}><I size={13} />{m.label}</span>
}

export function Stars({ value }: { value?: number | null }) {
  if (value == null) return <span className="faint">–</span>
  const tone = value <= 2 ? 'var(--neg-accent)' : value === 3 ? 'var(--warn-accent)' : 'var(--pos-accent)'
  return <span className="stars" title={`Predicted satisfaction ${value} of 5`} aria-label={`${value} of 5`}>
    {[1, 2, 3, 4, 5].map(i => <Star key={i} fill={i <= value ? tone : 'none'} stroke={i <= value ? tone : 'var(--line-strong)'} />)}
  </span>
}

export function RiskBadge({ value }: { value?: string }) {
  if (!value || value === 'low') return null
  return <span className={`pill ${value === 'high' ? 'bad' : 'warn'}`}><AlertTriangle size={12} />{value === 'high' ? 'High risk' : 'Some risk'}</span>
}

export function ComplianceBadge({ on }: { on?: boolean }) {
  return on ? <span className="pill bad"><ShieldAlert size={12} />Compliance</span> : null
}

export const ACTION_LABEL: Record<string, string> = {
  callback: 'Call back', offer: 'Send an offer', apology: 'Apologise', escalate: 'Escalate', ticket: 'Open a ticket',
  technician: 'Send a technician', refund_review: 'Review refund', coach_agent: 'Coach the agent', follow_up: 'Follow up',
  verify_info: 'Verify information',
}
export const OUTCOME_LABEL: Record<string, string> = {
  recovered: 'Customer recovered', offer_accepted: 'Offer accepted', resolved_later: 'Resolved later', no_answer: 'No answer',
  not_recovered: 'Not recovered',
}
export const PRIORITY_TONE: Record<string, string> = { high: 'bad', medium: 'warn', low: 'plain' }
export const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin', manager: 'Manager', qa: 'QA / Supervisor', retention: 'Retention', agent: 'Agent', executive: 'Executive',
}
