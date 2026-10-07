import { day, percent, taka } from '../format'

const RULES = {
  reported_number: 'Several different customers reported this number (medium or high confidence). Pauses any amount and skips the purpose question.',
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

function Block({ step, title, note, children }) {
  return (
    <section className="block">
      <div className="block-head">
        <span className="block-step">{step}</span>
        <div>
          <h3>{title}</h3>
          <p>{note}</p>
        </div>
      </div>
      {children}
    </section>
  )
}

export default function Inspector({ check }) {
  const d = check && check.details
  if (!check) {
    return (
      <div className="inspector">
        <p className="side-note">Run a payment and the engine's working appears here in three separate parts: what the models measured, which fixed rules fired, and how the message was worded.</p>
        <ol className="flow">
          <li><strong>1. Model signals</strong><span>LightGBM and Isolation Forest score the payment against this customer's own history.</span></li>
          <li><strong>2. Deterministic rules</strong><span>Purpose rules, reported numbers, bill cover and weekly spending. Plain code, no model.</span></li>
          <li><strong>3. Decision</strong><span>Silent, nudge or pause. Made by code from steps 1 and 2.</span></li>
          <li><strong>4. Wording</strong><span>Templates in Bangla and English. An LLM may only reword, and only if it keeps every number.</span></li>
        </ol>
      </div>
    )
  }

  const modelFired = d && d.flags && d.flags.behaviour
  const rulesFired = d && d.flags && (d.flags.rules || d.flags.shortfall)

  return (
    <div className="inspector">
      <div className="verdict">
        <span className={`pill kind-${check.decision === 'ask_purpose' ? 'ask' : check.decision}`}>{check.decision.replace('_', ' ')}</span>
        <span>{taka(check.amount || 0)} {check.type ? check.type.replace('_', ' ') : ''}</span>
        {check.risk_level && <span className="muted">risk level: {check.risk_level}</span>}
      </div>

      {check.decision === 'ask_purpose' && (
        <p className="side-note">
          {check.details.new_recipient ? 'New recipient. ' : ''}{check.details.label_confident ? '' : 'The label model is unsure. '}
          The engine replied ask_purpose and waits for the customer's answer before scoring. Most payments are never asked.
        </p>
      )}

      {d && d.risk && (
        <>
          <p className="side-note">
            Decided by: {modelFired && rulesFired ? 'the behaviour model and a fixed rule' : modelFired ? 'the behaviour model' : rulesFired ? 'a fixed rule' : check.decision === 'nudge' ? 'a coaching check, not a risk signal' : 'nothing fired, so the payment goes straight to OTP'}.
          </p>

          <Block step="1" title="Model signals" note="Measured by trained models. They score, they do not write text.">
            <dl className="kv">
              <div><dt>Scam probability (LightGBM)</dt><dd>{d.risk.probability.toFixed(3)}</dd></div>
            </dl>
            <Meter value={d.risk.probability} threshold={d.risk.threshold} />
            <dl className="kv">
              <div><dt>Anomaly score (Isolation Forest)</dt><dd>{d.risk.anomaly.toFixed(2)}</dd></div>
            </dl>
            <Meter value={d.risk.anomaly} threshold={d.risk.anomaly_threshold} />
            <p className="side-note">The marker is the pause level, fixed on a validation month. Model says: {d.risk.high ? 'high risk' : 'not high risk'}.</p>
            <h4>Compared with this customer's own history</h4>
            <dl className="kv">
              <div><dt>Usual amount for this type</dt><dd>{taka(d.features.usual_amount)}</dd></div>
              <div><dt>This payment</dt><dd>{d.features.amount_ratio}× usual</dd></div>
              <div><dt>Recipient</dt><dd>{d.features.new_recipient ? 'never paid before' : `paid ${d.features.times_paid_before} times`}</dd></div>
              <div><dt>Share of balance</dt><dd>{percent(Math.min(d.features.balance_share, 1))}</dd></div>
              <div><dt>Received from recipient, 72 h</dt><dd>{taka(d.features.received_from_recipient_72h)}</dd></div>
            </dl>
            <h4>What moved the score (SHAP)</h4>
            <ul className="shap">
              {d.risk.contributions.map((c) => (
                <li key={c.feature}>
                  <span>{c.label}</span>
                  <span className={c.shap >= 0 ? 'pos' : 'neg'}>{c.shap >= 0 ? '+' : ''}{c.shap.toFixed(2)}</span>
                </li>
              ))}
            </ul>
            {check.label && (
              <dl className="kv">
                <div><dt>Category label</dt><dd>{check.label.custom || check.label.category.replace('_', ' ')}</dd></div>
                <div><dt>Label confidence</dt><dd>{percent(check.label.confidence)} ({check.label.auto ? 'auto' : 'customer stated the purpose'})</dd></div>
              </dl>
            )}
          </Block>

          <Block step="2" title="Deterministic rules" note="Plain code outside the model. The same input always gives the same result.">
            {d.rules.length === 0 && <p className="side-note">No scam rule fired{d.purpose ? ` for the stated purpose "${d.purpose.replace('_', ' ')}"` : ''}.</p>}
            <ul className="plain">{d.rules.map((r) => <li key={r}>{RULES[r] || r}</li>)}</ul>
            {d.reported && (
              <p className="side-note">
                Reported-number check: {d.reported.reports === 0 ? 'no reports for this number.'
                  : `${d.reported.reports} ${d.reported.reports === 1 ? 'reporter' : 'different reporters'}, ${d.reported.recent_reports} in the last 30 days, score ${d.reported.score}, confidence ${d.reported.confidence}. ${d.reported.confidence === 'low' ? 'Below the pause level, so it only adds a caution.' : 'At or above the pause level.'}`}
              </p>
            )}
            {d.affordability ? (
              <p className="side-note">Bill check: {d.affordability.bill} ({taka(d.affordability.bill_amount)}) is due {day(d.affordability.due_date)}. This payment leaves {taka(d.affordability.shortfall)} too little.</p>
            ) : <p className="side-note">Bill check: bills due in the next 7 days stay covered.</p>}
            {d.nudge && (
              <p className="side-note">Spending check: {d.nudge.category.replace('_', ' ')} this week would reach {taka(d.nudge.week_total)} against a usual {taka(d.nudge.baseline)}.</p>
            )}
          </Block>

          <Block step="3" title="LLM explanation" note="The language model never decides and never sees the transaction. It can only reword a finished alert.">
            <dl className="kv">
              <div><dt>This message was written by</dt><dd>{check.explanation_source === 'llm' ? 'LLM rewording' : 'fixed template'}</dd></div>
              <div><dt>LLM configured</dt><dd>{d.llm && d.llm.configured ? 'yes' : 'no'}</dd></div>
              <div><dt>Data residency mode</dt><dd>{d.llm ? d.llm.residency.replace('_', ' ') : 'n/a'}</dd></div>
            </dl>
            <p className="side-note">
              A reworded message is thrown away unless it contains exactly the same numbers as the template and no links. With no LLM the app works the same, as it does now on this demo{d.llm && d.llm.active ? ' when the model does not answer' : ''}.
            </p>
          </Block>
        </>
      )}
    </div>
  )
}
