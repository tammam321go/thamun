import { percent } from '../format'

const fixed = (value, digits = 2) => (value === null || value === undefined ? 'no data' : (Math.round(Number(value) * 10 ** digits + 1e-6) / 10 ** digits).toFixed(digits))

function Bar({ value, max, tone }) {
  return <span className="bar-cell"><i className={tone || ''} style={{ width: `${Math.max(2, (value / max) * 100)}%` }} /></span>
}

export default function Evidence({ evidence }) {
  if (!evidence || !evidence.metrics) {
    return <p className="side-note">Evaluation files are not available yet. Run <code>python -m ml.evaluate</code> and <code>python -m ml.experiments</code>.</p>
  }
  const m = evidence.metrics
  const x = evidence.experiments
  const g = m.guard
  const pooled = x && x.stress && x.stress.new_customers_pooled
  return (
    <div className="evidence-tab">
      <p className="label-strip">Synthetic evaluation. No real customers or real transactions.</p>

      <div className="tiles">
        <div><b>{percent(g.recall_payments, 1)}</b><span>scam payments paused in the held-out month ({Math.round(g.recall_payments * g.scam_payments)} of {g.scam_payments})</span></div>
        {pooled && <div><b>{percent(pooled.recall, 1)}</b><span>on customers the models never saw ({pooled.scams_paused} of {pooled.scam_payments})</span></div>}
        <div><b>{fixed(g.false_pauses_per_customer_month)}</b><span>false pauses per customer per month{pooled ? ` (${fixed(pooled.false_pauses_per_customer_month)} on new customers)` : ''}</span></div>
        {m.friction && <div><b>{percent(m.friction.no_interruption, 1)}</b><span>of payments go straight to OTP, no question, no message</span></div>}
      </div>
      <p className="side-note">
        Test month {m.test_month}, {m.customers} simulated customers. The 95% interval for the first figure is {percent(g.recall_payments_interval[0], 1)} to {percent(g.recall_payments_interval[1], 1)}.
        {pooled ? ` For new customers it is ${percent(pooled.recall_interval[0], 1)} to ${percent(pooled.recall_interval[1], 1)}.` : ''}
      </p>

      {x && (
        <>
          <h3>Model comparison</h3>
          <p className="side-note">Same features, same split, same number of false pauses allowed in September.</p>
          <table className="fair">
            <thead><tr><th>Model</th><th>PR-AUC</th><th>Scams caught</th><th>ms</th></tr></thead>
            <tbody>
              {x.comparison.rows.filter((r) => r.pr_auc !== null).map((r) => (
                <tr key={r.model} className={r.model === 'LightGBM' ? 'chosen' : ''}>
                  <td>{r.model}</td><td>{fixed(r.pr_auc, 3)}</td><td>{r.scams_at_equal_budget} of {r.scam_payments}</td><td>{fixed(r.ms_per_payment, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="side-note">
            LightGBM and Random Forest are within one payment of each other, which is inside the noise for {x.data.test_scam_payments} scams. LightGBM is used because it scores a payment about {Math.round(x.comparison.rows[1].ms_per_payment / x.comparison.rows[2].ms_per_payment)} times faster and gives exact SHAP values.
            Honest finding: the Isolation Forest added {x.comparison.isolation_only_flags.scams} scam payments and {x.comparison.isolation_only_flags.legit} false pauses, so it runs as a safety net that still has to prove itself on real data.
          </p>

          <h3>Which signals matter (ablation)</h3>
          <p className="side-note">Scam payments caught when one signal group is removed from the model. Full model: {x.feature_ablation.production_set.scams_at_equal_budget} of {x.feature_ablation.production_set.scam_payments}.</p>
          <ul className="bars">
            {x.feature_ablation.leave_one_group_out.map((r) => (
              <li key={r.group}>
                <span>Without {r.removed.toLowerCase()}</span>
                <Bar value={r.scams_at_equal_budget} max={r.scam_payments} tone={r.scams_change <= -5 ? 'hot' : ''} />
                <b>{r.scams_at_equal_budget} ({r.scams_change})</b>
              </li>
            ))}
          </ul>
          <p className="side-note">With only the raw payment fields (amount, type) and no customer history the model catches {x.feature_ablation.cumulative[0].scams_at_equal_budget} of {x.feature_ablation.cumulative[0].scam_payments}. The value comes from comparing each customer with their own past.</p>

          <h3>Decision layers</h3>
          <table className="fair">
            <thead><tr><th>Layer</th><th>Scams paused</th><th>Genuine pauses</th></tr></thead>
            <tbody>
              {x.system_ablation.rows.map((r) => (
                <tr key={r.layer}><td>{r.layer}</td><td>{r.scams_paused} of {r.scam_payments}</td><td>{fixed(r.genuine_pauses_per_customer_month)}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="side-note">Genuine pauses are per customer per month. Scam-number reputation: not measured, because every simulated scam uses a number once.</p>

          <h3>A scam type it was never trained on</h3>
          <table className="fair">
            <thead><tr><th>Type hidden from training</th><th>Still caught</th></tr></thead>
            <tbody>
              {x.unseen_scam_types.rows.map((r) => (
                <tr key={r.scam_type}><td>{r.scam_type.replace(/_/g, ' ')}</td><td>{r.caught_with_isolation_forest} of {r.payments}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="side-note">Overall {percent(x.unseen_scam_types.overall_combined, 1)}. Impersonation through a known contact stays the blind spot.</p>

          {x.stress && (
            <>
              <h3>Stress test: what if the simulator is wrong?</h3>
              <p className="side-note">Models and thresholds frozen. New populations, nothing retrained.</p>
              <table className="fair">
                <thead><tr><th>Population</th><th>Paused</th><th>False pauses</th></tr></thead>
                <tbody>
                  {x.stress.rows.map((r) => (
                    <tr key={r.id}><td>{r.name}</td><td>{percent(r.recall, 1)} ({r.scams_paused}/{r.scam_payments})</td><td>{fixed(r.false_pauses_per_customer_month)}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <h3>Calibration</h3>
          <p className="side-note">Brier score {x.calibration.brier_raw} raw, {x.calibration.brier_calibrated} after isotonic calibration, {x.calibration.brier_always_base_rate} for always guessing the base rate. Decisions use the ranking, so calibration changes no decision.</p>
        </>
      )}

      <h3>Fairness by persona</h3>
      <table className="fair">
        <thead><tr><th>Persona</th><th>Scams paused</th><th>False pauses</th></tr></thead>
        <tbody>
          {Object.entries(m.guard_by_persona).map(([name, row]) => (
            <tr key={name}><td>{name.replace('_', ' ')}</td><td>{percent(row.recall_payments)}</td><td>{fixed(row.false_pauses_per_customer_month)}</td></tr>
          ))}
        </tbody>
      </table>

      <h3>What this does not show</h3>
      <ul className="plain limits">
        <li>Real customers and real transactions: not yet measured.</li>
        <li>Every number above comes from one simulator written by the team.</li>
        <li>Scams are injected far more often than in real life, so precision would be lower in production.</li>
      </ul>
    </div>
  )
}
