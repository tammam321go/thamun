import { useState } from 'react'
import { api } from '../api'

export default function ReportBox({ customerId, number, lang, t, options, already, onDone }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [count, setCount] = useState(null)
  const [error, setError] = useState('')

  const send = async (pattern) => {
    setBusy(true)
    setError('')
    try {
      const data = await api.report({ customer_id: customerId, number, pattern, lang })
      setCount(data.reports)
      if (onDone) onDone(data)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  if (count !== null) {
    return <p className="report-done" role="status">{count <= 1 ? t('reportThanksOne') : t('reportThanks', { count })}</p>
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
