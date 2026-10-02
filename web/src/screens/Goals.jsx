import { useEffect, useState } from 'react'
import { api } from '../api'
import { taka } from '../format'

export default function Goals({ customerId, lang, t, version, onChanged }) {
  const [goal, setGoal] = useState(undefined)
  const [target, setTarget] = useState('30000')
  const [months, setMonths] = useState('6')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let stopped = false
    api.goal(customerId, lang).then((d) => !stopped && setGoal(d.goal)).catch(() => !stopped && setGoal(null))
    return () => {
      stopped = true
    }
  }, [customerId, version, lang])

  const plan = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const data = await api.setGoal(customerId, Number(target), Number(months), lang)
      setGoal(data.goal)
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      const data = await api.saveToGoal(customerId, goal.per_week, lang)
      setGoal(data.goal)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  return (
    <div className="pad stack">
      <h1>{t('goalTitle')}</h1>
      <form className="goal-form" onSubmit={plan}>
        <label className="field">
          <span>{t('target')}</span>
          <div className="money"><span>৳</span><input value={target} inputMode="numeric" onChange={(e) => setTarget(e.target.value.replace(/\D/g, ''))} /></div>
        </label>
        <label className="field narrow">
          <span>{t('months')}</span>
          <input value={months} inputMode="numeric" onChange={(e) => setMonths(e.target.value.replace(/\D/g, ''))} />
        </label>
        <button className="btn primary" disabled={busy || !Number(target) || !Number(months)}>{t('makePlan')}</button>
      </form>
      {error && <p className="error">{error}</p>}

      {goal && (
        <>
          <section className="plan">
            <div className="plan-figure">
              <strong>{taka(goal.per_month)}</strong><span>{t('perMonth')}</span>
            </div>
            <div className="plan-figure">
              <strong>{taka(goal.per_week)}</strong><span>{t('perWeek')}</span>
            </div>
            <span className={`pill ${goal.level === 'realistic' ? 'ready' : goal.level === 'stretch' ? 'tight' : 'short'}`}>{t(goal.level)}</span>
          </section>

          {goal.cuts.length > 0 && (
            <section>
              <h2>{t('cuts')}</h2>
              <ul className="rows">
                {goal.cuts.map((c) => (
                  <li key={c.category}>
                    <div className="row-main">
                      <span className="row-title">{c.name}</span>
                      <span className="row-sub">{taka(c.monthly_spend)} {t('perMonth')}</span>
                    </div>
                    <div className="row-side"><span className="row-amount">{t('lessPerWeek', { amount: taka(c.weekly_cut) })}</span></div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <div className="bar"><i style={{ width: `${Math.min(goal.progress.percent, 100)}%` }} /></div>
            <p className="footnote">{t('savedSoFar', { a: taka(goal.progress.saved), b: taka(goal.target) })}</p>
            <button className="btn amber" disabled={busy} onClick={save}>{t('saveNow', { amount: taka(goal.per_week) })}</button>
          </section>
        </>
      )}
    </div>
  )
}
