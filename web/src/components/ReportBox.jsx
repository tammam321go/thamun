import { useState } from 'react'
import { api } from '../api'

export default function ReportBox({ customerId, number, lang, t, options, already, onDone }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const [error, setError] = useState('')

  const send = async (pattern) => {
    setBusy(true)
    setError('')
    try {
      const data = await api.report({ customer_id: customerId, number, pattern, lang })
      setDone(data)
      if (onDone) onDone(data)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  if (done) {
    const strong = done.confidence === 'medium' || done.confidence === 'high'
    const text = strong ? t('reportThanks', { count: done.reports })
      : done.reports <= 1 ? t('reportThanksOne') : t('reportThanksFew', { count: done.reports })
    return <p className="report-done" role="status">{text}</p>
  }
  if (already) return <p className="report-done">{t('reportedByYou')}</p>

  return (
    <div className="report">
      {!open && <button type="button" className="btn report-btn" onClick={() => setOpen(true)}>{t('reportBtn')}</button>}
      {open && (
        <>
          <p className="report-ask">{t('reportWhy')}</p>
          <div className="chips column">
            {(options || []).map((o) => (
              <button type="button" key={o.code} className="chip wide" disabled={busy} onClick={() => send(o.code)}>{o.label}</button>
            ))}
          </div>
        </>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}
