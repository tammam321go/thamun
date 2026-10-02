import { useState } from 'react'
import { api } from '../api'

export default function Ask({ customerId, lang, t }) {
  const [question, setQuestion] = useState('')
  const [thread, setThread] = useState([])
  const [busy, setBusy] = useState(false)

  const ask = async (text) => {
    const q = text.trim()
    if (q.length < 2 || busy) return
    setBusy(true)
    setQuestion('')
    try {
      const data = await api.ask(customerId, q, lang)
      setThread((items) => [...items, { q, a: data.answer, source: data.source }])
    } catch (e) {
      setThread((items) => [...items, { q, a: e.message, source: 'error' }])
    }
    setBusy(false)
  }

  return (
    <div className="pad stack ask">
      <h1>{t('askTitle')}</h1>
      <div className="chips column">
        {['q1', 'q2', 'q3', 'q4'].map((k) => (
          <button key={k} className="chip wide" disabled={busy} onClick={() => ask(t(k))}>{t(k)}</button>
        ))}
      </div>
      <div className="thread" aria-live="polite">
        {thread.map((item, i) => (
          <div key={i} className="qa">
            <p className="q">{item.q}</p>
            <p className="a">{item.a}</p>
            {item.source !== 'error' && <p className="footnote">{item.source === 'llm' ? t('wordedByAi') : t('fromNumbers')}</p>}
          </div>
        ))}
        {busy && <p className="muted">…</p>}
      </div>
      <form className="inline ask-box" onSubmit={(e) => { e.preventDefault(); ask(question) }}>
        <input value={question} maxLength={300} placeholder={t('askHint')} onChange={(e) => setQuestion(e.target.value)} aria-label={t('askHint')} />
        <button className="btn primary" disabled={busy || question.trim().length < 2}>{t('askSend')}</button>
      </form>
    </div>
  )
}
