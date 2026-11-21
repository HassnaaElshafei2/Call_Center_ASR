import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { FileAudio, Upload } from '@/components/icons'
import { api } from '@/lib/api'
import { Modal, useToast } from './ui'
import { useEnt } from './Shell'

export function UploadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { ent, base, meta, current } = useEnt()
  const [files, setFiles] = useState<File[]>([])
  const [agent, setAgent] = useState('')
  const [started, setStarted] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const toast = useToast()
  const qc = useQueryClient()
  const nav = useNavigate()
  const submit = async () => {
    setBusy(true); setErr('')
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    if (agent) fd.append('agent_id', agent)
    if (started) fd.append('started_at', started)
    try {
      const r = await api<{ created: string[] }>(`/e/${ent}/calls/upload`, { method: 'POST', body: fd })
      toast(`${r.created.length} call${r.created.length === 1 ? '' : 's'} uploaded: transcription and analysis started`)
      qc.invalidateQueries({ queryKey: ['calls'] })
      setFiles([]); onClose()
      nav(r.created.length === 1 ? `${base}/calls/${r.created[0]}` : `${base}/calls?status=queued,waiting_asr,transcribing,analyzing,done&period=today`)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const agents = (meta?.agents || []).filter((a: any) => a.enterprise === ent && a.active)
  return (
    <Modal open={open} onClose={onClose} narrow icon={Upload} title="Upload calls" sub={`${current?.name}: recordings are transcribed with our Egyptian Arabic model, then analysed`}>
      <label className="card" style={{ padding: 22, borderStyle: 'dashed', textAlign: 'center', cursor: 'pointer' }}
        onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); setFiles([...files, ...Array.from(e.dataTransfer.files)]) }}>
        <input type="file" multiple accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac,.opus,.amr" hidden onChange={e => setFiles([...files, ...Array.from(e.target.files || [])])} />
        <FileAudio size={26} style={{ color: 'var(--brand)' }} />
        <div className="strong" style={{ marginTop: 6 }}>Drop recordings here or click to choose</div>
        <div className="small muted">WAV, MP3, M4A, OGG, FLAC. {ent === 'btech' ? 'B.TECH names like btech_01012345678.mp3 link the call to that customer.' : 'One file per call.'}</div>
      </label>
      {!!files.length && <div className="stack small" style={{ gap: 4 }}>{files.map((f, i) => <div key={i} className="row"><FileAudio size={14} />{f.name}<span className="muted right">{(f.size / 1e6).toFixed(1)} MB</span></div>)}</div>}
      <div className="grid g2">
        <label className="field">Agent (optional)<select className="input" value={agent} onChange={e => setAgent(e.target.value)}>
          <option value="">Unknown / detect later</option>{agents.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        <label className="field">Call time (optional)<input className="input" type="datetime-local" value={started} onChange={e => setStarted(e.target.value)} /></label>
      </div>
      {!meta?.services?.asr && <div className="pill warn" style={{ height: 'auto', padding: '8px 12px', whiteSpace: 'normal' }}>The transcription service isn't connected yet: uploads will wait and be transcribed as soon as it is.</div>}
      {err && <div className="pill bad" style={{ height: 'auto', padding: '8px 12px' }}>{err}</div>}
      <div className="row"><button className="btn right" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!files.length || busy} onClick={submit}>{busy ? 'Uploading…' : `Upload ${files.length || ''}`}</button></div>
    </Modal>
  )
}
