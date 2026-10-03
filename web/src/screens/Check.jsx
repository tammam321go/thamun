import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import ReportBox from '../components/ReportBox'

const looksValid = (value) => value.replace(/[^A-Za-z0-9]/g, '').length >= 4

export default function Check({ customerId, lang, t, preset, version, onChanged, onSendTo }) {
  const [number, setNumber] = useState('')
  const [asked, setAsked] = useState('')
  const [data, setData] = useState(null)
  const [list, setList] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [tick, setTick] = useState(0)
  const [options, setOptions] = useState([])
  const [target, setTarget] = useState('')
  const [choosing, setChoosing] = useState(false)
  const [sending, setSending] = useState(false)
  const [outcome, setOutcome] = useState(null)
  const [reportError, setReportError] = useState('')
  const seen = useRef(null)

  useEffect(() => {
    if (!preset || seen.current === preset.nonce) return
    seen.current = preset.nonce
    setNumber(preset.number)
    setAsked(preset.number)
  }, [preset])

  useEffect(() => {
    let stopped = false
    api.reportOptions(lang).then((rows) => !stopped && setOptions(rows)).catch(() => {})
    return () => {
      stopped = true
    }
  }, [lang])

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
    if (!looksValid(typed)) {
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

  const startReport = (e) => {
    e.preventDefault()
    setOutcome(null)
    if (!looksValid(target.trim())) {
      setChoosing(false)
      return setReportError(t('badNumber'))
    }
    setReportError('')
    return setChoosing(true)
  }

  const sendReport = async (pattern) => {
    setSending(true)
    setReportError('')
    try {
      const result = await api.report({ customer_id: customerId, number: target.trim(), pattern, lang })
      setOutcome({ added: result.added, reports: result.reports, number: result.number })
      setChoosing(false)
      setTarget('')
      setNumber(result.number)
      setAsked(result.number)
      reported()
    } catch (e) {
      setReportError(e.message === 'Enter the number using digits only.' ? t('badNumber') : e.message)
    }
    setSending(false)
  }

  const thanks = outcome && (!outcome.added ? t('reportedByYou')
    : outcome.reports <= 1 ? t('reportThanksOne') : t('reportThanks', { count: outcome.reports }))

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
          {data.reports > 0 && <button type="button" className="link send-try" onClick={() => onSendTo(data.number)}>{t('sendToThis')}</button>}
        </section>
      )}

      <section>
        <h2>{t('reportTitle')}</h2>
        <p className="muted">{t('reportIntro')}</p>
        <form className="check-form report-form" onSubmit={startReport}>
          <input value={target} inputMode="numeric" maxLength={24} placeholder={t('numberHint')} aria-label={t('reportHint')}
            onChange={(e) => { setTarget(e.target.value); setChoosing(false); setOutcome(null); setReportError('') }} />
          <button className="btn danger">{t('reportGo')}</button>
        </form>
        {choosing && (
          <div className="report report-form">
            <p className="report-ask">{t('reportWhy')}</p>
            <div className="chips column">
              {options.map((o) => (
                <button type="button" key={o.code} className="chip wide" disabled={sending} onClick={() => sendReport(o.code)}>{o.label}</button>
              ))}
            </div>
          </div>
        )}
        {thanks && <p className="report-done report-form" role="status">{outcome.number}: {thanks}</p>}
        {reportError && <p className="error">{reportError}</p>}
      </section>

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
