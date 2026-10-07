import { useEffect, useState } from 'react'
import { api } from '../api'
import { taka } from '../format'
import Icon from './Icon'

const COPY = {
  bill: { title: 'Pay a bill that is due', expect: 'A known biller and the usual amount go straight to OTP. Most payments are never interrupted.' },
  routine: { title: 'Pay a regular shop', expect: 'Nothing unusual, so no extra step.' },
  friend: { title: 'Send the usual amount to a regular contact', expect: 'Known person, normal amount, no extra step.' },
  food: { title: 'Order food again', expect: 'A one-line spending note if this week is already above the customer\'s usual. This is coaching, not a fraud alert.' },
  refund: { title: 'Return money "sent by mistake"', ask: 'Thamun asks the purpose once. Choose "Returning money sent to me by mistake".', expect: 'It pauses: no money ever arrived from that number. Open "Why did Thamun pause this?" and then cancel.' },
  prize: { title: 'Pay a fee to claim a prize', ask: 'Thamun asks the purpose. Choose "Fee to claim a prize, cashback or offer".', expect: 'It pauses on the stated purpose and on behaviour.' },
  takeover: { title: 'Cash out almost everything at an unknown agent', expect: 'Pauses on behaviour alone. This is what an account takeover looks like.' },
  reported_small: { title: 'Send a tiny amount to a reported number', expect: 'Pauses at once, even for ৳50, because many different customers reported it.' },
  reported_usual: { title: 'Send a normal amount to a reported number', expect: 'Pauses without asking the purpose.' },
  reported_once: { title: 'Send to a number with a single report', expect: 'A caution, not a pause. One report is not proof, so nobody can block a number by reporting it once.' },
  bill_risk: { title: 'Send a large amount just before bills are due', ask: 'Thamun asks the purpose. Choose "Paying or lending to a friend".', expect: 'A different kind of pause: a bill warning in teal, not a scam alert in red. The recipient is a trusted contact and the risk model is calm.' },
}
const STORY = [['bill', 'routine', 'friend'], ['food'], ['refund'], ['reported_small'], ['reported_once'], ['bill_risk']]

const PERSONA = {
  salaried: 'Salaried worker. Salary on the 1st, rent, family support and five regular bills.',
  student: 'Student. Small, frequent payments and a monthly allowance.',
  shop_owner: 'Shop owner. Many incoming payments and large supplier payments.',
  irregular: 'Irregular income. Money arrives on unpredictable days and leaves quickly.',
}

export default function DemoGuide({ customer, customerId, version, testing, onTesting, onRun, onGo, onPanel, onCheckNumber, onSendTo, onReset, onClose }) {
  const [script, setScript] = useState([])
  const [reported, setReported] = useState([])

  useEffect(() => {
    let stopped = false
    api.script(customerId).then((d) => !stopped && setScript(d)).catch(() => {})
    api.reports().then((d) => !stopped && setReported(d)).catch(() => {})
    return () => {
      stopped = true
    }
  }, [customerId, version])

  const byId = Object.fromEntries(script.map((s) => [s.id, s]))
  const story = STORY.map((ids) => ids.map((id) => byId[id]).find(Boolean)).filter(Boolean)
  const used = new Set(story.map((s) => s.id))
  const others = script.filter((s) => !used.has(s.id))

  const step = (s) => {
    const kind = s.expected || s.kind
    return (
      <li key={s.id}>
        <div className="step-top">
          <span className="step-title">{(COPY[s.id] || {}).title}</span>
          <span className={`pill kind-${kind}`}>{s.pause_kind === 'bill' ? 'bill pause' : kind}</span>
        </div>
        <p>{s.asks_purpose && (COPY[s.id] || {}).ask ? `${COPY[s.id].ask} ` : ''}{(COPY[s.id] || {}).expect}{s.reports ? ` ${s.counterparty} has ${s.reports} ${s.reports === 1 ? 'report' : 'reports'} (${s.confidence} confidence).` : ''}</p>
        <button className="btn small" onClick={() => onRun(s)}>Run with {taka(s.amount)}</button>
      </li>
    )
  }

  return (
    <div className="guide">
      <div className="side-head">
        <h2>Demo guide</h2>
        <button className="icon-btn close" onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
      </div>

      <div className="problem">
        <p className="problem-kicker">Pause. Understand. Decide.</p>
        <p><strong>The problem.</strong> In Bangladesh, scammers phone or message mobile wallet users and talk them into sending the money themselves: a "refund", a "prize fee", a fake agent. The customer types their own PIN and OTP, so to the wallet it looks like a normal payment.</p>
        <p><strong>Thamun</strong> protects users from socially engineered mobile financial service payments before OTP. It is an explainable AI financial safety layer for Bangladesh's mobile financial services ecosystem. It does not decide for the customer. It gives them a moment to decide.</p>
      </div>

      {customer && <p className="persona"><strong>{customer.name}.</strong> {PERSONA[customer.persona]}</p>}

      <h3>Demo story</h3>
      <ol className="steps numbered">
        {story.map(step)}
        <li>
          <div className="step-top"><span className="step-title">Look under the hood</span></div>
          <p>Every decision is split into model signals, fixed rules and wording. The other tabs hold the test evidence, the impact numbers and live system health.</p>
          <div className="guide-actions">
            <button className="link" onClick={() => onPanel('decision')}>Decision</button>
            <button className="link" onClick={() => onPanel('evidence')}>Evidence</button>
            <button className="link" onClick={() => onPanel('impact')}>Impact</button>
            <button className="link" onClick={() => onPanel('system')}>System</button>
          </div>
        </li>
      </ol>

      <h3>User testing mode</h3>
      <label className="switch">
        <input type="checkbox" checked={testing} onChange={(e) => onTesting(e.target.checked)} />
        <span>{testing ? 'On. After each warning the phone asks five short questions.' : 'Off. Turn on, then hand the phone to someone.'}</span>
      </label>
      <p className="side-note">Answers are stored without a name, a number or a session id, and are counted in the Impact tab. No real OTP, PIN or account is ever asked for.</p>

      <h3>More scenarios</h3>
      <ol className="steps">
        {others.map(step)}
      </ol>

      <h3>Reported numbers</h3>
      <p className="side-note">Kept in the database. Confidence comes from how many different customers reported a number and how recently. Medium and high pause any amount, low only adds a caution. Report a new number as three different demo customers to watch it move from low to medium.</p>
      <ul className="guide-list">
        {reported.map((r) => (
          <li key={r.number}>
            <code>{r.number}</code>
            <span>{r.reports} {r.reports === 1 ? 'report' : 'reports'} · {r.confidence}</span>
            <span className="guide-actions">
              <button className="link" onClick={() => onSendTo(r.number)}>Send</button>
              <button className="link" onClick={() => onCheckNumber(r.number)}>Check</button>
            </span>
          </li>
        ))}
      </ul>

      <h3>Then look at the coach</h3>
      <ul className="jumps">
        <li><button className="link" onClick={() => onGo('home')}>Home</button> shows protection, this week's spending, bills and the savings goal.</li>
        <li><button className="link" onClick={() => onGo('review')}>Review</button> shows where the month went and what changed.</li>
        <li><button className="link" onClick={() => onGo('goals')}>Goals</button> turns "save ৳30,000 in 6 months" into a weekly plan.</li>
        <li><button className="link" onClick={() => onGo('ask')}>Ask</button> answers "Why do I run short before month-end?"</li>
      </ul>

      <p className="side-note">Switch customer at the top of the phone to see the same rules applied to a student, a shop owner and an irregular earner. Each one is compared with their own history.</p>
      <button className="btn" onClick={onReset}>Reset the demo</button>
    </div>
  )
}
