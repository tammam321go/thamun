import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import Icon from '../components/Icon'
import ReportBox from '../components/ReportBox'
import { day, taka } from '../format'

const TYPES = ['send_money', 'merchant_payment', 'bill_payment', 'cash_out', 'mobile_recharge']
const FREE_ENTRY = { send_money: true, cash_out: true }
const REPORTABLE = { send_money: true, cash_out: true }

export default function Pay({ customerId, lang, t, home, preset, onPresetUsed, onCheck, onChanged, onHome }) {
  const [step, setStep] = useState('form')
  const [type, setType] = useState('send_money')
  const [book, setBook] = useState(null)
  const [target, setTarget] = useState(null)
  const [number, setNumber] = useState('')
  const [amount, setAmount] = useState('')
  const [payment, setPayment] = useState(null)
  const [options, setOptions] = useState([])
  const [ownLabel, setOwnLabel] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [otp, setOtp] = useState('')
  const [agree, setAgree] = useState(false)
  const [callTip, setCallTip] = useState(false)
  const [receipt, setReceipt] = useState(null)
  const [editing, setEditing] = useState(false)
  const [reported, setReported] = useState(false)
  const seen = useRef(null)
  const amountBox = useRef(null)
  const [warn, setWarn] = useState(null)

  useEffect(() => {
    let stopped = false
    api.payees(customerId, lang).then((data) => !stopped && setBook(data)).catch(() => {})
    return () => {
      stopped = true
    }
  }, [customerId, lang])

  useEffect(() => {
    const screen = document.querySelector('.screen')
    if (screen) screen.scrollTop = 0
  }, [step])

  useEffect(() => {
    const typed = number.trim()
    if (!FREE_ENTRY[type] || typed.replace(/[^A-Za-z0-9]/g, '').length < 11) {
      setWarn(null)
      return undefined
    }
    let stopped = false
    api.checkNumber(customerId, typed, lang)
      .then((data) => !stopped && setWarn(data.reports > 0 ? data.reports : null))
      .catch(() => !stopped && setWarn(null))
    return () => {
      stopped = true
    }
  }, [number, type, customerId, lang])

  const runCheck = async (pay, purpose, label) => {
    setBusy(true)
    setError('')
    try {
      const body = { customer_id: customerId, type: pay.type, counterparty: pay.counterparty, counterparty_name: pay.name, amount: Number(pay.amount), lang }
      if (pay.merchant_type && pay.merchant_type !== 'none') body.merchant_type = pay.merchant_type
      if (purpose) body.purpose = purpose
      if (label) body.custom_label = label
      const data = await api.check(body)
      onCheck({ ...data, type: pay.type })
      if (data.decision === 'insufficient') {
        setError(t('insufficient'))
        setStep('form')
      } else if (data.decision === 'ask_purpose') {
        setOptions(data.purpose_options)
        setStep('purpose')
      } else {
        setResult(data)
        setOtp('')
        setAgree(false)
        setCallTip(false)
        setReported(Boolean(data.details.reported && data.details.reported.you_reported))
        setStep(data.decision === 'pause' ? 'pause' : 'otp')
      }
    } catch (e) {
      setError(e.message)
      setStep('form')
    }
    setBusy(false)
  }

  useEffect(() => {
    if (!preset || seen.current === preset.nonce) return
    seen.current = preset.nonce
    onPresetUsed()
    setType(preset.type)
    setError('')
    setReceipt(null)
    setOwnLabel('')
    if (preset.blank || preset.prefill) {
      setTarget(null)
      setNumber(preset.prefill ? preset.counterparty : '')
      setAmount('')
      setStep('form')
      if (preset.prefill) setTimeout(() => amountBox.current && amountBox.current.focus(), 80)
      return
    }
    const name = preset.fresh ? preset.counterparty : preset.name
    const pay = { type: preset.type, counterparty: preset.counterparty, name, amount: preset.amount, merchant_type: preset.merchant_type }
    setTarget({ counterparty: preset.counterparty, name, merchant_type: preset.merchant_type })
    setNumber(FREE_ENTRY[preset.type] && preset.fresh ? preset.counterparty : '')
    setAmount(String(preset.amount))
    setPayment(pay)
    runCheck(pay)
  }, [preset])

  const submit = (e) => {
    e.preventDefault()
    const typed = number.trim()
    if (typed && !/^[A-Za-z0-9-]{2,24}$/.test(typed)) return setError(t('badNumber'))
    const chosen = typed ? { counterparty: typed, name: typed, merchant_type: 'none' } : target
    if (!chosen) return setError(t('pickPayee'))
    if (!(Number(amount) > 0)) return setError(t('enterAmount'))
    const pay = { type, counterparty: chosen.counterparty, name: chosen.name, amount: Number(amount), merchant_type: chosen.merchant_type }
    setPayment(pay)
    return runCheck(pay)
  }

  const finish = async (action) => {
    setBusy(true)
    setError('')
    try {
      const data = await api.pay({ customer_id: customerId, check_id: result.check_id, action, otp: action === 'proceed' ? otp : undefined })
      setReceipt(data)
      setStep(action === 'cancel' ? 'cancelled' : 'done')
      onChanged()
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  const relabel = async (category) => {
    const data = await api.label({ customer_id: customerId, txn_id: receipt.txn.txn_id, category }).catch(() => null)
    if (data) setReceipt({ ...receipt, txn: { ...receipt.txn, category, category_name: book.categories.find((c) => c.code === category)?.label } })
    setEditing(false)
    onChanged()
  }

  const restart = () => {
    setStep('form')
    setTarget(null)
    setNumber('')
    setAmount('')
    setResult(null)
    setReceipt(null)
    setOwnLabel('')
    setError('')
  }

  const text = result ? (result.i18n && result.i18n[lang]) || result : null
  const labelName = result && result.label ? result.label.custom || (result.label.names && result.label.names[lang]) || result.label.name : ''
  const categoryName = (code, fallback) => (book && book.categories.find((c) => c.code === code)?.label) || fallback
  const reportBox = result && REPORTABLE[payment.type] ? (
    <ReportBox key={result.check_id} customerId={customerId} number={result.counterparty} lang={lang} t={t}
      options={book ? book.report_options : []} already={reported} onDone={() => { setReported(true); onChanged() }} />
  ) : null

  if (step === 'purpose') {
    const choices = (book && book.purposes) || options
    return (
      <div className="pad stack">
        <button className="link" onClick={() => setStep('form')}>{t('back')}</button>
        <div>
          <h1>{t('purposeTitle')}</h1>
          <p className="muted">{taka(payment.amount)} · {payment.name}</p>
        </div>
        <div className="chips column">
          {choices.map((o) => (
            <button key={o.code} className="chip wide" disabled={busy} onClick={() => runCheck(payment, o.code, ownLabel.trim())}>{o.label}</button>
          ))}
        </div>
        <label className="field">
          <span>{t('ownLabel')}</span>
          <div className="inline">
            <input value={ownLabel} maxLength={30} placeholder={t('ownLabelHint')} onChange={(e) => setOwnLabel(e.target.value)} />
            <button className="btn" disabled={busy || !ownLabel.trim()} onClick={() => runCheck(payment, 'other', ownLabel.trim())}>{t('next')}</button>
          </div>
        </label>
        <p className="footnote">{t('purposeNote')}</p>
      </div>
    )
  }

  if (step === 'pause') {
    return (
      <div className="pause" role="alertdialog" aria-labelledby="pause-title">
        <div className="pause-word" aria-hidden="true">{t('pauseWord')}</div>
        <h1 id="pause-title">{text.headline}</h1>
        <p className="pause-sum">{taka(result.amount)} · {result.counterparty_name}</p>
        {text.source === 'llm' && <p className="pause-lead">{text.message}</p>}
        <ul className="reasons">
          {text.reasons.map((r) => <li key={r.code}>{r.text}</li>)}
        </ul>
        <p className="pause-advice">{text.advice}</p>
        <div className="pause-actions">
          <button className="btn light" disabled={busy} onClick={() => finish('cancel')}>{t('cancelPay')}</button>
          <button className="btn ghost" onClick={() => setCallTip(!callTip)}>{t('callFirst', { name: result.trusted_name || '…' })}</button>
          {callTip && <p className="pause-tip">{t('callTip')}</p>}
          {reportBox}
          <label className="agree">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            <span>{t('readIt')}</span>
          </label>
          <button className="btn outline" disabled={!agree} onClick={() => setStep('otp')}>{t('proceed')}</button>
        </div>
      </div>
    )
  }

  if (step === 'otp') {
    return (
      <div className="pad stack">
        <button className="link" onClick={() => setStep(result.decision === 'pause' ? 'pause' : 'form')}>{t('back')}</button>
        <h1>{t('confirmTitle')}</h1>
        {result.decision === 'nudge' && (
          <div className="nudge" role="status">
            <strong>{text.headline}</strong>
            <p>{text.message}</p>
          </div>
        )}
        <dl className="summary">
          <div><dt>{t('payTo')}</dt><dd>{result.counterparty_name}</dd></div>
          <div><dt>{t('amount')}</dt><dd>{taka(result.amount)}</dd></div>
          <div><dt>{t('labelled')}</dt><dd><span className="tag">{labelName}</span></dd></div>
          <div><dt>{t('balanceAfter')}</dt><dd>{taka(result.balance_after)}</dd></div>
        </dl>
        <label className="field">
          <span>OTP</span>
          <input className="otp" inputMode="numeric" maxLength={4} value={otp} placeholder="• • • •" autoFocus
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))} />
        </label>
        <p className="footnote">{t('otpNote')}</p>
        {error && <p className="error">{error}</p>}
        <button className="btn primary" disabled={busy || otp.length !== 4} onClick={() => finish('proceed')}>{t('payNow', { amount: taka(result.amount) })}</button>
        <button className="btn" disabled={busy} onClick={() => finish('cancel')}>{t('cancelPay')}</button>
      </div>
    )
  }

  if (step === 'done' && receipt) {
    return (
      <div className="pad stack centre">
        <div className="tick"><Icon name="check" size={30} /></div>
        <h1>{t('paid')}</h1>
        <p className="big">{taka(receipt.txn.amount)}</p>
        <p className="muted">{receipt.txn.name}</p>
        <div className="label-edit">
          <span>{t('labelled')}</span>
          <span className="tag">{receipt.txn.label || categoryName(receipt.txn.category, receipt.txn.category_name)}</span>
          <button className="link" onClick={() => setEditing(!editing)}>{t('change')}</button>
        </div>
        {editing && book && (
          <div className="chips">
            {book.categories.map((c) => (
              <button key={c.code} className={`chip ${c.code === receipt.txn.category ? 'on' : ''}`} onClick={() => relabel(c.code)}>{c.label}</button>
            ))}
          </div>
        )}
        <p className="muted">{t('balance')}: {taka(receipt.balance)}</p>
        <button className="btn primary" onClick={onHome}>{t('done')}</button>
        <button className="btn" onClick={restart}>{t('another')}</button>
      </div>
    )
  }

  if (step === 'cancelled' && receipt) {
    return (
      <div className="pad stack centre">
        <div className="tick safe"><Icon name="check" size={30} /></div>
        <h1>{t('cancelled')}</h1>
        <p>{t('stayed', { amount: taka(result.amount) })}</p>
        <p className="muted">{t('balance')}: {taka(receipt.balance)}</p>
        {result.decision === 'pause' && reportBox}
        <button className="btn primary" onClick={onHome}>{t('done')}</button>
        <button className="btn" onClick={restart}>{t('another')}</button>
      </div>
    )
  }

  const list = book && !(FREE_ENTRY[type] && number.trim()) ? book.payees[type] || [] : []

  return (
    <form className="pad stack" onSubmit={submit}>
      <div className="types" role="tablist">
        {TYPES.map((name) => (
          <button type="button" key={name} role="tab" aria-selected={type === name} className={type === name ? 'on' : ''}
            onClick={() => { setType(name); setTarget(null); setNumber(''); setError('') }}>
            <span className="action-icon"><Icon name={name} size={20} /></span>
            <span>{t(name)}</span>
          </button>
        ))}
      </div>

      <div>
        <h2>{t('payTo')}</h2>
        {FREE_ENTRY[type] && (
          <label className="field">
            <span>{t('newNumber')}</span>
            <input value={number} inputMode="numeric" placeholder={t('numberHint')} maxLength={24}
              onChange={(e) => { setNumber(e.target.value); setTarget(null) }} />
          </label>
        )}
        {FREE_ENTRY[type] && warn && <p className="number-warn" role="status">{warn === 1 ? t('reportedWarnOne') : t('reportedWarn', { n: warn })}</p>}
        {list.length > 0 && <div className="list-label">{t('saved')}</div>}
        {book && list.length === 0 && !FREE_ENTRY[type] && <p className="muted">{t('noPayees')}</p>}
        <ul className="rows pick">
          {list.map((p) => (
            <li key={p.counterparty}>
              <button type="button" className={target && target.counterparty === p.counterparty && !number ? 'on' : ''}
                onClick={() => { setTarget(p); setNumber(''); if (type === 'bill_payment') setAmount(String(p.usual_amount)) }}>
                <span className="row-main">
                  <span className="row-title">{p.name}</span>
                  <span className="row-sub">{p.due_date ? `${t('due')} ${day(p.due_date, lang)}` : t('usual', { amount: taka(p.usual_amount) })}</span>
                </span>
                {p.due_date && <span className="row-amount">{taka(p.usual_amount)}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <label className="field">
        <span>{t('amount')}</span>
        <div className="money">
          <span>৳</span>
          <input ref={amountBox} value={amount} inputMode="decimal" placeholder="0" onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} />
        </div>
      </label>
      {home && <p className="footnote">{t('balance')}: {taka(home.balance)}</p>}
      {error && <p className="error">{error}</p>}
      <button className="btn primary" disabled={busy}>{busy ? '…' : t('next')}</button>
    </form>
  )
}
