import { day, percent, taka } from '../format'
import Icon from './Icon'

const RULES = {
  reported_number: 'Several different customers reported this number (medium or high confidence). This pauses any amount and skips the purpose question.',
  refund_no_incoming: 'Refund claimed, but nothing was received from this number in the last 72 hours.',
  refund_exceeds_incoming: 'Refund claimed for more than was received.',
  prize_fee: 'Stated purpose is a fee for a prize or offer.',
  agent_request: 'Stated purpose is a request made over the phone.',
}

function Meter({ value, threshold }) {
  return (
    <div className="meter">
      <i style={{ width: `${Math.min(value, 1) * 100}%` }} className={value >= threshold ? 'hot' : ''} />
      <b style={{ left: `${Math.min(threshold, 1) * 100}%` }} />
    </div>
  )
}

function Evidence({ metrics }) {
  if (!metrics) return null
  const g = metrics.guard
  return (
    <details className="evidence">
      <summary>Tested on a month the models never saw</summary>
      <dl className="kv">
        <div><dt>Scam payments paused</dt><dd>{percent(g.recall_payments, 1)} of {g.scam_payments}</dd></div>
        <div><dt>False pauses per customer a month</dt><dd>{g.false_pauses_per_customer_month.toFixed(2)}</dd></div>
        <div><dt>Payments not asked for a purpose</dt><dd>{percent(metrics.labels.not_asked_share, 1)}</dd></div>
        <div><dt>Auto-label accuracy</dt><dd>{percent(metrics.labels.auto_label_accuracy, 1)}</dd></div>
        <div><dt>Recurring bills found</dt><dd>{percent(metrics.bills.detection_recall, 1)}</dd></div>
        <div><dt>Nudges in truly above-usual weeks</dt><dd>{percent(metrics.nudges.precision_truly_above_usual, 1)}</dd></div>
      </dl>
      <table className="fair">
        <thead><tr><th>Persona</th><th>Scams paused</th><th>False pauses</th></tr></thead>
        <tbody>
          {Object.entries(metrics.guard_by_persona).map(([name, m]) => (
            <tr key={name}><td>{name.replace('_', ' ')}</td><td>{percent(m.recall_payments)}</td><td>{m.false_pauses_per_customer_month.toFixed(2)}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="side-note">Synthetic data, {metrics.customers} customers, test month {metrics.test_month}. Scam attempts are oversampled.</p>
    </details>
  )
}

export default function Inspector({ check, metrics, onClose }) {
  const d = check && check.details
  return (
    <div className="inspector">
      <div className="side-head">
        <h2>Why it decided</h2>
        <button className="icon-btn close" onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
      </div>

      {!check && <p className="side-note">Run a payment and the engine's working appears here: the label, the risk score, the rules that fired and the bill check.</p>}

      {check && (
        <>
          <div className="verdict">
            <span className={`pill kind-${check.decision === 'ask_purpose' ? 'ask' : check.decision}`}>{check.decision.replace('_', ' ')}</span>
            <span>{taka(check.amount || 0)} {check.type ? check.type.replace('_', ' ') : ''}</span>
          </div>

          {check.decision === 'ask_purpose' && (
            <p className="side-note">
              {check.details.new_recipient ? 'New recipient. ' : ''}{check.details.label_confident ? '' : 'The label model is unsure. '}
              The engine replied ask_purpose and waits for the customer's answer before scoring.
            </p>
          )}

          {check.label && check.decision !== 'ask_purpose' && (
            <section>
              <h3>Label</h3>
              <dl className="kv">
                <div><dt>Category</dt><dd>{check.label.custom || check.label.category.replace('_', ' ')}</dd></div>
                <div><dt>Model confidence</dt><dd>{percent(check.label.confidence)}</dd></div>
                <div><dt>Source</dt><dd>{check.label.auto ? 'auto-labelled' : 'customer stated the purpose'}</dd></div>
              </dl>
            </section>
          )}

          {d && d.risk && (
            <>
              <section>
                <h3>Behaviour model</h3>
                <dl className="kv">
                  <div><dt>Scam probability (LightGBM)</dt><dd>{d.risk.probability.toFixed(3)}</dd></div>
                </dl>
                <Meter value={d.risk.probability} threshold={d.risk.threshold} />
                <dl className="kv">
                  <div><dt>Anomaly score (Isolation Forest)</dt><dd>{d.risk.anomaly.toFixed(2)}</dd></div>
                </dl>
                <Meter value={d.risk.anomaly} threshold={d.risk.anomaly_threshold} />
                <p className="side-note">The marker is the pause threshold, chosen on a validation month.</p>
              </section>

              <section>
                <h3>Compared with this customer's history</h3>
                <dl className="kv">
                  <div><dt>Usual amount for this type</dt><dd>{taka(d.features.usual_amount)}</dd></div>
                  <div><dt>This payment</dt><dd>{d.features.amount_ratio}× usual</dd></div>
                  <div><dt>Recipient</dt><dd>{d.features.new_recipient ? 'never paid before' : `paid ${d.features.times_paid_before} times`}</dd></div>
                  <div><dt>Share of balance</dt><dd>{percent(Math.min(d.features.balance_share, 1))}</dd></div>
                  <div><dt>Received from recipient, 72 h</dt><dd>{taka(d.features.received_from_recipient_72h)}</dd></div>
                </dl>
              </section>

              <section>
                <h3>What moved the score (SHAP)</h3>
                <ul className="shap">
                  {d.risk.contributions.map((c) => (
                    <li key={c.feature}>
                      <span>{c.label}</span>
                      <span className={c.shap >= 0 ? 'pos' : 'neg'}>{c.shap >= 0 ? '+' : ''}{c.shap.toFixed(2)}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section>
                <h3>Rules, kept outside the model</h3>
                {d.rules.length === 0 && <p className="side-note">No rule fired{d.purpose ? ` for "${d.purpose.replace('_', ' ')}"` : ''}.</p>}
                <ul className="plain">{d.rules.map((r) => <li key={r}>{RULES[r] || r}</li>)}</ul>
                {d.reported && (
                  <p className="side-note">
                    Community reports: {d.reported.reports === 0 ? 'none for this number.'
                      : `${d.reported.reports} reporters, ${d.reported.recent_reports} in the last 30 days, score ${d.reported.score}, confidence ${d.reported.confidence}. ${d.reported.confidence === 'low' ? 'Below the pause level, so it only adds a caution.' : ''}`}
                  </p>
                )}
                {d.affordability ? (
                  <p className="side-note">Bill check: {d.affordability.bill} ({taka(d.affordability.bill_amount)}) is due {day(d.affordability.due_date)}. This payment leaves {taka(d.affordability.shortfall)} too little.</p>
                ) : <p className="side-note">Bill check: bills due in the next 7 days stay covered.</p>}
                {d.nudge && (
                  <p className="side-note">Spending check: {d.nudge.category.replace('_', ' ')} this week would reach {taka(d.nudge.week_total)} against a usual {taka(d.nudge.baseline)}.</p>
                )}
              </section>

              <p className="side-note">Wording: {check.explanation_source === 'llm' ? 'rephrased by an LLM from the reasons above; it cannot change the decision.' : 'fixed templates filled with the numbers above.'}</p>
            </>
          )}
        </>
      )}

      <Evidence metrics={metrics} />
    </div>
  )
}
