import { useState } from 'react'
import { api } from '../api'
import Icon from '../components/Icon'
import { clock, day, taka } from '../format'

const TYPES = ['send_money', 'merchant_payment', 'bill_payment', 'cash_out', 'mobile_recharge']

export default function Home({ home, t, lang, customerId, onPay, onVerify, onChanged }) {
  const [busy, setBusy] = useState(false)
  if (!home) return <div className="pad muted">…</div>
  const { bills } = home
  const soon = bills.bills.filter((b) => b.days_left <= 21)

  const cashIn = async (amount) => {
    setBusy(true)
    await api.cashIn(customerId, amount).catch(() => {})
    setBusy(false)
    onChanged()
  }

  return (
    <div className="pad stack">
      <section className="balance">
        <div className="balance-label">{t('balance')}</div>
        <div className="balance-value">{taka(home.balance)}</div>
        <div className="balance-name">{home.customer.name}</div>
        {home.protected > 0 && <div className="protected">{taka(home.protected)} {t('protected')}</div>}
      </section>

      <section className="actions" aria-label={t('pay')}>
        {TYPES.map((type) => (
          <button key={type} onClick={() => onPay(type)}>
            <span className="action-icon"><Icon name={type} size={20} /></span>
            <span>{t(type)}</span>
          </button>
        ))}
      </section>

      <button className="scam-card" onClick={onVerify}>
        <span className="action-icon"><Icon name="verify" size={20} /></span>
        <span>
          <strong>{t('scamCard')}</strong>
          <small>{t('scamCardSub')}</small>
        </span>
      </button>

      <section>
        <h2>{t('bills')}</h2>
        {soon.length === 0 && <p className="muted">{t('noBills')}</p>}
        {bills.reminder && (
          <div className="reminder">
            <p>{t('reminder', { amount: taka(bills.reminder.amount), date: day(bills.reminder.cash_in_by, lang), bill: bills.reminder.bill })}</p>
            <button className="btn amber" disabled={busy} onClick={() => cashIn(bills.reminder.amount)}>
              {t('cashIn', { amount: taka(bills.reminder.amount) })}
            </button>
          </div>
        )}
        <ul className="rows">
          {soon.map((b) => (
            <li key={b.counterparty}>
              <div className="row-main">
                <span className="row-title">{b.name}</span>
                <span className="row-sub">{b.overdue ? t('overdue') : `${t('due')} ${day(b.due_date, lang)}`}</span>
              </div>
              <div className="row-side">
                <span className="row-amount">{taka(b.amount)}</span>
                <span className={`pill ${b.status}`}>{t(b.status)}</span>
              </div>
            </li>
          ))}
        </ul>
        {bills.daily_spend > 0 && <p className="footnote">{t('spendPerDay', { amount: taka(bills.daily_spend) })}</p>}
      </section>

      <section>
        <h2>{t('recent')}</h2>
        <ul className="rows">
          {home.recent.map((x) => (
            <li key={x.txn_id}>
              <div className="row-main">
                <span className="row-title">{x.name}</span>
                <span className="row-sub">{day(x.ts, lang)}, {clock(x.ts)} · {x.label || x.category_name}</span>
              </div>
              <div className="row-side">
                <span className={`row-amount ${x.direction === 'in' ? 'in' : ''}`}>{x.direction === 'in' ? '+' : '−'}{taka(x.amount)}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
