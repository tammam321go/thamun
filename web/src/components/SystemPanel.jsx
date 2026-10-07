import { useEffect, useState } from 'react'
import { api } from '../api'
import { percent } from '../format'

const ms = (value) => (value === null || value === undefined ? 'no data' : `${Number(value).toFixed(1)} ms`)
const BACKENDS = { sqlite: 'SQLite file', postgresql: 'PostgreSQL' }

export default function SystemPanel({ evidence, active }) {
  const [live, setLive] = useState(null)

  useEffect(() => {
    if (!active) return undefined
    let stopped = false
    const load = () => api.monitoring().then((d) => !stopped && setLive(d)).catch(() => {})
    load()
    const timer = setInterval(load, 5000)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [active])

  const test = evidence && evidence.load_test
  return (
    <div className="system">
      <p className="label-strip">Live counters from this API process. Demo traffic, refreshed every 5 seconds.</p>
      {!live && <p className="side-note">Loading…</p>}
      {live && (
        <>
          <h3>Health</h3>
          <dl className="kv">
            <div><dt>Requests handled</dt><dd>{live.requests} ({live.requests_last_minute} in the last minute)</dd></div>
            <div><dt>Server error rate</dt><dd>{percent(live.error_rate, 2)}</dd></div>
            <div><dt>Requests rate-limited</dt><dd>{live.rate_limited}</dd></div>
            <div><dt>Risk check latency, median</dt><dd>{ms(live.latency_check.p50_ms)}</dd></div>
            <div><dt>Risk check latency, 95th percentile</dt><dd>{ms(live.latency_check.p95_ms)}</dd></div>
            <div><dt>Uptime</dt><dd>{Math.floor(live.uptime_seconds / 60)} min</dd></div>
          </dl>

          <h3>Decisions since start</h3>
          <dl className="kv">
            <div><dt>Silent / nudge / pause</dt><dd>{live.decisions.silent || 0} / {live.decisions.nudge || 0} / {live.decisions.pause || 0}</dd></div>
            <div><dt>Purpose questions</dt><dd>{live.decisions.ask_purpose || 0}</dd></div>
          </dl>

          <h3>Model drift watch</h3>
          <dl className="kv">
            <div><dt>Status</dt><dd>{live.drift.status}</dd></div>
            <div><dt>Live checks collected</dt><dd>{live.drift.live_checks} (needs {live.drift.minimum_sample})</dd></div>
            <div><dt>Score shift (PSI)</dt><dd>{live.drift.score_psi === null ? 'no data' : live.drift.score_psi}</dd></div>
            <div><dt>High-risk share, live vs reference</dt><dd>{live.drift.high_risk_share === null || live.drift.high_risk_share === undefined ? 'no data' : percent(live.drift.high_risk_share, 1)} vs {live.drift.reference_high_risk_share === undefined ? 'no data' : percent(live.drift.reference_high_risk_share, 1)}</dd></div>
          </dl>
          <p className="side-note">Demo payments are scripted, so drift here only shows that the check works. In production a PSI above 0.25 opens a review before any retraining.</p>

          <h3>Platform</h3>
          <dl className="kv">
            <div><dt>Database</dt><dd>{BACKENDS[live.database.backend] || live.database.backend} ({live.database.ok ? 'ok' : 'down'}{live.database.fallback ? ', fallback: PostgreSQL was unreachable' : ''})</dd></div>
            <div><dt>Session token required</dt><dd>{live.security.auth_required ? 'yes' : 'no'}</dd></div>
            <div><dt>Rate limit</dt><dd>{live.security.rate_limit_per_minute} requests a minute</dd></div>
            <div><dt>Allowed web origins</dt><dd>{live.security.cors_origins.join(', ')}</dd></div>
            <div><dt>LLM data residency</dt><dd>{live.llm.residency.replace('_', ' ')}{live.llm.active ? '' : ' (LLM off)'}</dd></div>
            <div><dt>Models trained</dt><dd>{String(live.model.trained_at).replace('T', ' ')}</dd></div>
          </dl>
        </>
      )}

      <h3>Load test</h3>
      {!test && <p className="side-note">Not yet measured on this deployment. Run <code>python -m loadtest.run</code>.</p>}
      {test && (
        <>
          <dl className="kv">
            <div><dt>Simulated users</dt><dd>{test.users}</dd></div>
            <div><dt>Requests</dt><dd>{test.requests} in {test.duration_seconds} s</dd></div>
            <div><dt>Throughput</dt><dd>{test.requests_per_second} requests a second</dd></div>
            <div><dt>Failures</dt><dd>{test.failures} ({percent(test.failure_rate, 2)})</dd></div>
            <div><dt>Risk check, median / 95th / 99th</dt><dd>{test.check.p50_ms} / {test.check.p95_ms} / {test.check.p99_ms} ms</dd></div>
          </dl>
          <table className="fair">
            <thead><tr><th>Users</th><th>Requests a second</th><th>Check, 95th percentile</th><th>Failures</th></tr></thead>
            <tbody>
              {test.stages.map((s) => (
                <tr key={s.users} className={s.users === test.users ? 'chosen' : ''}><td>{s.users}</td><td>{s.requests_per_second}</td><td>{s.check.p95_ms} ms</td><td>{s.failures}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="side-note">One worker stays fast up to about {test.users} simultaneous users and then queues. More users need more workers, which has not been measured. {test.environment}</p>
        </>
      )}

      <h3>Where it would run in production</h3>
      <ul className="plain limits">
        <li>Inside the wallet provider's own data centre in Bangladesh. No customer data crosses the border.</li>
        <li>The risk models are small files that run on ordinary CPUs next to the payment service.</li>
        <li>Any language model is hosted internally. A public LLM API is refused by default.</li>
        <li>Stateless API workers behind a load balancer, PostgreSQL for records, Redis for live counters.</li>
      </ul>
    </div>
  )
}
