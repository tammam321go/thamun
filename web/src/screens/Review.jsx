import { useEffect, useState } from 'react'
import { api } from '../api'
import Donut, { PALETTE } from '../components/Donut'
import { monthName, taka } from '../format'

export default function Review({ customerId, lang, t, version }) {
  const [month, setMonth] = useState(null)
  const [data, setData] = useState(null)

  useEffect(() => {
    let stopped = false
    api.review(customerId, month, lang).then((d) => !stopped && setData(d)).catch(() => {})
    return () => {
      stopped = true
    }
  }, [customerId, month, lang, version])

  if (!data) return <div className="pad muted">…</div>
  const top = data.categories.slice(0, 6)
  const rest = data.categories.slice(6).reduce((sum, c) => sum + c.amount, 0)
  const slices = rest > 0 ? [...top, { name: t('otherCats'), amount: rest, category: 'rest' }] : top
  const delta = data.previous_total_out ? Math.round(((data.total_out - data.previous_total_out) / data.previous_total_out) * 100) : null

  return (
    <div className="pad stack">
      <div className="chips">
        {[...data.months].reverse().map((m) => (
          <button key={m} className={`chip ${m === data.month ? 'on' : ''}`} onClick={() => setMonth(m)}>{monthName(m, lang)}</button>
        ))}
      </div>

      <section className="review-head">
        <Donut slices={slices} centre={taka(data.total_out)} caption={t('monthOut')} />
        <div className="review-facts">
          <div><span className="muted">{t('monthIn')}</span><strong>{taka(data.total_in)}</strong></div>
          <div><span className="muted">{t('monthOut')}</span><strong>{taka(data.total_out)}</strong></div>
          {data.partial ? <p className="footnote">{t('soFar')}</p>
            : delta !== null && <p className="footnote">{delta > 0 ? '+' : ''}{delta}% {t('vsLast', { month: monthName(data.previous_month, lang) })}</p>}
        </div>
      </section>

      <section>
        <h2>{t('byCategory')}</h2>
        <ul className="rows">
          {slices.map((c, i) => (
            <li key={c.category}>
              <div className="row-main with-dot">
                <i className="dot" style={{ background: PALETTE[i % PALETTE.length] }} />
                <span className="row-title">{c.name}</span>
              </div>
              <div className="row-side">
                <span className="row-amount">{taka(c.amount)}</span>
                {c.change_pct !== null && c.change_pct !== undefined && c.change_pct !== 0 && (
                  <span className={`delta ${c.change_pct > 0 ? 'up' : 'down'}`}>{c.change_pct > 0 ? '+' : ''}{c.change_pct}%</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>

      {data.increases.length > 0 && (
        <section>
          <h2>{t('changes')}</h2>
          <ul className="plain">
            {data.increases.map((c) => (
              <li key={c.category}>{c.name}: {taka(c.amount)}, {t('up')} {c.change_pct}% {t('vsLast', { month: monthName(data.previous_month, lang) })}</li>
            ))}
            {data.decreases.map((c) => (
              <li key={c.category}>{c.name}: {taka(c.amount)}, {t('down')} {Math.abs(c.change_pct)}%</li>
            ))}
          </ul>
        </section>
      )}

      {data.pattern && <p className="insight">{t('pattern', { share: data.pattern.share_first_10_days })}</p>}

      <section className="two">
        <div className="panel">
          <h3>{t('rewards')} <span className="tag soft">{t('simulated')}</span></h3>
          <div className="points">{data.rewards.points}</div>
          <p className="footnote">{t('billsOnTime', { a: data.rewards.bills_on_time, b: data.rewards.bills_paid })}</p>
          {data.rewards.goal_on_track && <p className="footnote">{t('goalTrack')}</p>}
        </div>
        <div className="panel">
          <h3>{t('guard')}</h3>
          <p className="footnote">{t('guardLine', { pauses: data.guard.pauses, cancelled: data.guard.cancelled, amount: taka(data.guard.protected) })}</p>
          <p className="footnote">{t('nudgeLine', { n: data.nudges })}</p>
        </div>
      </section>
    </div>
  )
}
