import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import ReportBox from '../components/ReportBox'

export default function Check({ customerId, lang, t, preset, version, onChanged }) {
  const [number, setNumber] = useState('')
  const [asked, setAsked] = useState('')
  const [data, setData] = useState(null)
  const [list, setList] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [tick, setTick] = useState(0)
  const seen = useRef(null)

  useEffect(() => {
    if (!preset || seen.current === preset.nonce) return
    seen.current = preset.nonce
    setNumber(preset.number)
    setAsked(preset.number)
  }, [preset])

  useEffect(() => {
    let stopped = false
    api.reports().then((rows) => !stopped && setList(rows)).catch(() => {})
    return () => {
      stopped = true
    }
  }, [tick, version])

  useEffect(() => {
    if (!asked) return undefined
    let stopped = false
    setBusy(true)
    setError('')
    api.checkNumber(customerId, asked, lang)
      .then((result) => !stopped && setData(result))
      .catch((e) => {
        if (stopped) return
        setData(null)
        setError(e.message === 'Enter the number using digits only.' ? t('badNumber') : e.message)
      })
      .finally(() => !stopped && setBusy(false))
    return () => {
      stopped = true
    }
  }, [asked, lang, customerId, tick])

  const submit = (e) => {
    e.preventDefault()
    const typed = number.trim()
    if (typed.replace(/[^A-Za-z0-9]/g, '').length < 4) {
      setData(null)
      setAsked('')
      return setError(t('badNumber'))
    }
    setAsked(typed)
    return setTick((n) => n + 1)
  }

  const pick = (value) => {
    setNumber(value)
    setAsked(value)
  }

  const reported = () => {
    setTick((n) => n + 1)
    onChanged()
  }

  return (
    <div className="pad stack">
      <div>
        <h1>{t('checkTitle')}</h1>
        <p className="muted">{t('checkIntro')}</p>
      </div>

      <form className="check-form" onSubmit={submit}>
        <input value={number} inputMode="numeric" maxLength={24} placeholder={t('numberHint')} aria-label={t('checkHint')}
          onChange={(e) => setNumber(e.target.value)} />
        <button className="btn primary" disabled={busy}>{t('checkBtn')}</button>
      </form>
      {error && <p className="error">{error}</p>}

      {data && (
        <section className={`verdict-card ${data.verdict}`} aria-live="polite">
          <div>
            <div className="verdict-number">{data.number}</div>
            {data.name && <div className="muted">{data.name}</div>}
          </div>
          {data.reports > 0 && (
            <div className="verdict-count">{data.reports}<small>{data.reports === 1 ? t('reportWord') : t('reportsWord')}</small></div>
          )}
          <h2>{data.headline}</h2>
          <ul className="plain">
            {data.lines.map((line) => <li key={line}>{line}</li>)}
          </ul>
          <p className="verdict-advice">{data.advice}</p>
          {data.can_report && (
            <ReportBox key={`${data.number}-${customerId}`} customerId={customerId} number={data.number} lang={lang} t={t}
              options={data.report_options} already={data.you_reported} onDone={reported} />
          )}
        </section>
      )}

      <section>
        <h2>{t('reportedList')}</h2>
        <ul className="rows reported-list">
          {list.map((row) => (
            <li key={row.number}>
              <button type="button" onClick={() => pick(row.number)}>
                <span className="row-title">{row.number}</span>
                <span className="pill short">{t(row.reports === 1 ? 'reportsOne' : 'reportsN', { n: row.reports })}</span>
              </button>
            </li>
          ))}
        </ul>
        <p className="footnote">{t('demoList')}</p>
      </section>
    </div>
  )
}
