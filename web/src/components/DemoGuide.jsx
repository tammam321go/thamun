import { useEffect, useState } from 'react'
import { api } from '../api'
import { taka } from '../format'
import Icon from './Icon'

const COPY = {
  bill: { title: 'Pay a bill that is due', expect: 'Silent. A known biller and the usual amount go straight to OTP.' },
  routine: { title: 'Pay a regular shop', expect: 'Silent. Nothing unusual, so no extra step.' },
  food: { title: 'Order food again', expect: 'Nudge if this week is already above the customer\'s usual, otherwise silent.' },
  refund: { title: 'Return money "sent by mistake"', expect: 'Asks the purpose. Choose "Returning money sent to me by mistake" and Thamun pauses: no money ever arrived from that number.' },
  prize: { title: 'Pay a fee to claim a prize', expect: 'Asks the purpose. Choose "Fee to claim a prize" and Thamun pauses.' },
  takeover: { title: 'Cash out almost everything at an unknown agent', expect: 'Pauses on behaviour alone. This is what an account takeover looks like.' },
  friend: { title: 'Send the usual amount to a regular contact', expect: 'Silent. Known person, normal amount.' },
}

const PERSONA = {
  salaried: 'Salaried worker. Salary on the 1st, rent, family support and five regular bills.',
  student: 'Student. Small, frequent payments and a monthly allowance.',
  shop_owner: 'Shop owner. Many incoming payments and large supplier payments.',
  irregular: 'Irregular income. Money arrives on unpredictable days and leaves quickly.',
}

export default function DemoGuide({ customer, customerId, version, onRun, onGo, onReset, onClose }) {
  const [script, setScript] = useState([])

  useEffect(() => {
    let stopped = false
    api.script(customerId).then((d) => !stopped && setScript(d)).catch(() => {})
    return () => {
      stopped = true
    }
  }, [customerId, version])

  return (
    <div className="guide">
      <div className="side-head">
        <h2>Demo guide</h2>
        <button className="icon-btn close" onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
      </div>
      {customer && <p className="persona"><strong>{customer.name}.</strong> {PERSONA[customer.persona]}</p>}

      <h3>Try a payment</h3>
      <ol className="steps">
        {script.map((s) => (
          <li key={s.id}>
            <div className="step-top">
              <span className="step-title">{(COPY[s.id] || {}).title}</span>
              <span className={`pill kind-${s.kind}`}>{s.kind}</span>
            </div>
            <p>{(COPY[s.id] || {}).expect}</p>
            <button className="btn small" onClick={() => onRun(s)}>Run with {taka(s.amount)}</button>
          </li>
        ))}
      </ol>

      <h3>Then look at the coach</h3>
      <ul className="jumps">
        <li><button className="link" onClick={() => onGo('home')}>Home</button> shows which bills are covered and when to cash in.</li>
        <li><button className="link" onClick={() => onGo('review')}>Review</button> shows where the month went and what changed.</li>
        <li><button className="link" onClick={() => onGo('goals')}>Goals</button> turns "save ৳30,000 in 6 months" into a weekly plan.</li>
        <li><button className="link" onClick={() => onGo('ask')}>Ask</button> answers "Why do I run short before month-end?"</li>
      </ul>

      <p className="side-note">Switch customer at the top of the phone to see the same rules applied to a student, a shop owner and an irregular earner. Each one is compared with their own history.</p>
      <button className="btn" onClick={onReset}>Reset the demo</button>
    </div>
  )
}
