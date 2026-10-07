import { useEffect, useState } from 'react'
import { api } from '../api'
import { percent, taka } from '../format'

const fixed = (value, digits = 2) => (value === null || value === undefined ? 'no data' : (Math.round(Number(value) * 10 ** digits + 1e-6) / 10 ** digits).toFixed(digits))
const QUESTIONS = {
  understood_warning: 'Understood the warning',
  understood_reason: 'Understood why Thamun paused',
  intrusive: 'Felt too intrusive',
  understood_choice: 'Knew they could still decide',
}

function Row({ label, value, tag }) {
  return <div><dt>{label}{tag && <em className={`src ${tag}`}>{tag === 'sim' ? 'simulation' : tag === 'live' ? 'this session' : 'not yet measured'}</em>}</dt><dd>{value}</dd></div>
}

export default function Impact({ evidence, version }) {
  const [usage, setUsage] = useState(null)
  const [answers, setAnswers] = useState(null)

  useEffect(() => {
    let stopped = false
    api.analytics('session').then((d) => !stopped && setUsage(d)).catch(() => {})
    api.feedbackSummary().then((d) => !stopped && setAnswers(d)).catch(() => {})
    return () => {
      stopped = true
    }
  }, [version])

  const m = evidence && evidence.metrics
  const exportSummary = () => {
    const body = { exported_at: new Date().toISOString(), note: 'Anonymous totals only. No names, numbers or session ids.', prototype_use: usage, user_testing: answers }
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' }))
    link.download = 'thamun_user_testing_summary.json'
    link.click()
    URL.revokeObjectURL(link.href)
  }

  return (
    <div className="impact">
      <p className="label-strip">Three sources, kept apart: simulation, this demo session, and real users (not yet measured).</p>

      <h3>Safety</h3>
      <dl className="kv">
        {m && <Row tag="sim" label="Scam payments paused before OTP" value={percent(m.guard.recall_payments, 1)} />}
        {m && <Row tag="sim" label="Scam money paused" value={percent(m.guard.recall_money, 1)} />}
        {m && <Row tag="sim" label="Incidents stopped at the first payment" value={percent(m.guard.recall_first_payment, 1)} />}
        {usage && <Row tag="live" label="Pauses shown" value={usage.decisions.pause} />}
        {usage && <Row tag="live" label="Cancelled after a pause" value={`${usage.pauses_cancelled} (${percent(usage.cancellation_rate_after_pause)})`} />}
        {usage && <Row tag="live" label="Amount kept after a pause" value={taka(usage.amount_kept_after_pause)} />}
        {usage && <Row tag="live" label="Scam reports filed" value={usage.scam_reports_filed} />}
        <Row tag="none" label="Real fraud losses prevented" value="not measured" />
      </dl>

      <h3>Customer experience</h3>
      <dl className="kv">
        {m && m.friction && <Row tag="sim" label="Payments with no interruption at all" value={percent(m.friction.no_interruption, 1)} />}
        {m && m.friction && <Row tag="sim" label="Asked what the payment is for" value={percent(m.friction.asked_purpose, 1)} />}
        {m && m.friction && <Row tag="sim" label="Genuine payments paused" value={percent(m.friction.legit_paused, 1)} />}
        {m && <Row tag="sim" label="False pauses per customer per month" value={fixed(m.guard.false_pauses_per_customer_month)} />}
        {usage && <Row tag="live" label="Silent / nudge / pause" value={`${usage.decisions.silent} / ${usage.decisions.nudge} / ${usage.decisions.pause}`} />}
        {usage && <Row tag="live" label="Continued anyway after a pause" value={`${usage.pauses_continued} (${percent(usage.override_rate_after_pause)})`} />}
        <Row tag="none" label="Drop-off or complaints from real users" value="not measured" />
      </dl>

      <h3>Financial health</h3>
      <dl className="kv">
        {m && <Row tag="sim" label="Recurring bills found" value={percent(m.bills.detection_recall, 1)} />}
        {m && <Row tag="sim" label="Shortfalls flagged 3 days ahead" value={percent(m.bills.shortfall_recall_3_days_ahead, 1)} />}
        {m && <Row tag="sim" label="Nudges in truly above-usual weeks" value={percent(m.nudges.precision_truly_above_usual, 1)} />}
        {usage && <Row tag="live" label="Nudges continued / cancelled" value={`${usage.nudges_continued} / ${usage.nudges_cancelled}`} />}
        <Row tag="none" label="Bills paid on time, money saved by real users" value="not measured" />
      </dl>

      <h3>User testing</h3>
      {answers && answers.responses === 0 && <p className="side-note">No responses yet. Turn on user testing mode in the demo guide, hand the phone to someone, and their answers are counted here.</p>}
      {answers && answers.responses > 0 && (
        <>
          <p className="side-note">{answers.responses} {answers.responses === 1 ? 'response' : 'responses'} typed into this prototype. People tried scripted demo payments, not their own money.</p>
          <table className="fair">
            <thead><tr><th>Question</th><th>Yes</th><th>Partly</th><th>No</th></tr></thead>
            <tbody>
              {Object.entries(QUESTIONS).map(([key, label]) => (
                <tr key={key}><td>{label}</td><td>{answers.questions[key].yes}</td><td>{answers.questions[key].partly}</td><td>{answers.questions[key].no}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="side-note">Preferred language: Bangla {answers.preferred_language.bn}, English {answers.preferred_language.en}, both {answers.preferred_language.both}.</p>
        </>
      )}
      <button className="btn small" onClick={exportSummary}>Export anonymous summary (JSON)</button>
      <p className="side-note">The export holds totals only. Raw rows need the admin key and never include a name, a phone number or a session id.</p>
    </div>
  )
}
