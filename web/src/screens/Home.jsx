import { useState } from 'react'
import { api } from '../api'
import Icon from '../components/Icon'
import { clock, day, taka } from '../format'

const TYPES = ['send_money', 'merchant_payment', 'bill_payment', 'cash_out', 'mobile_recharge']

export default function Home({ home, t, lang, customerId, onPay, onVerify, onGoals, onChanged }) {
  const [busy, setBusy] = useState(false)
  if (!home) return <div className="pad muted">…</div>
  const { bills, protection, spending, goal } = home
  const soon = bills.bills.filter((b) => b.days_left <= 21)
  const active = (spending || []).filter((s) => s.usual_week > 0)

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
        <p className="tagline">{t('tagline')}</p>
      </section>

      <section className="actions" aria-label={t('pay')}>
        {TYPES.map((type) => (
          <button key={type} onClick={() => onPay(type)}>
            <span className="action-icon"><Icon name={type} size={20} /></span>
            <span>{t(type)}</span>
          </button>
        ))}
      </section>

      <section className="card protect">
        <div className="card-head">
          <span className="action-icon"><Icon name="verify" size={20} /></span>
          <div>
            <h2>{t('protectTitle')}</h2>
            <p>{t('protectSub')}</p>
          </div>
        </div>
        {protection && (
          <dl className="stats">
            <div><dd>{protection.checked}</dd><dt>{t('statChecked')}</dt></div>
            <div><dd>{protection.pauses}</dd><dt>{t('statPauses')}</dt></div>
            <div><dd>{protection.cancelled}</dd><dt>{t('statCancelled')}</dt></div>
            <div><dd>{taka(protection.kept_safe)}</dd><dt>{t('statKept')}</dt></div>
          </dl>
        )}
        <button className="btn danger-soft" onClick={onVerify}>{t('scamCardSub')}</button>
      </section>

      <div className="divider"><span>{t('coachTitle')}</span></div>

      {active.length > 0 && (
        <section className="card">
          <h2>{t('spendTitle')}</h2>
          <ul className="spend">
            {active.map((s) => {
              const over = s.ratio > 1.25
              return (
                <li key={s.category}>
                  <div className="spend-top">
                    <span className="row-title">{s.name}</span>
                    <span className={over ? 'over' : ''}>{taka(s.week_total)} <small>/ {t('usualShort', { amount: taka(s.usual_week) })}</small></span>
                  </div>
                  <div className="spend-bar"><i className={over ? 'over' : ''} style={{ width: `${Math.min(100, (s.ratio / 1.5) * 100)}%` }} /><b /></div>
                </li>
              )
            })}
          </ul>
          <p className="footnote">{t('spendNote')}</p>
        </section>
      )}

      <section className="card">
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

      <section className="card">
        <h2>{t('goalTitle')}</h2>
        {goal ? (
          <>
            <p>{t('savedSoFar', { a: taka(goal.progress.saved), b: taka(goal.target) })}</p>
            <div className="spend-bar"><i style={{ width: `${Math.min(100, (goal.progress.saved / goal.target) * 100)}%` }} /></div>
            <p className="footnote">{taka(goal.per_week)} {t('perWeek')}</p>
          </>
        ) : <p className="muted">{t('goalEmpty')}</p>}
        <button className="btn" onClick={onGoals}>{goal ? t('goalOpen') : t('goalStart')}</button>
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
