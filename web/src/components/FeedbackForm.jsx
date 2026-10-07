import { useState } from 'react'
import { api } from '../api'

const QUESTIONS = ['understood_warning', 'understood_reason', 'intrusive', 'understood_choice']
const ANSWERS = ['yes', 'partly', 'no']

export default function FeedbackForm({ scenario, decision, lang, t }) {
  const [values, setValues] = useState({})
  const [comment, setComment] = useState('')
  const [state, setState] = useState('open')
  const [error, setError] = useState('')
  const ready = QUESTIONS.every((q) => values[q]) && values.preferred_lang

  const send = async () => {
    setState('sending')
    setError('')
    try {
      await api.feedback({ scenario: scenario || 'free', decision, lang, ...values, comment: comment.trim() || undefined })
      setState('done')
    } catch (e) {
      setError(e.message)
      setState('open')
    }
  }

  if (state === 'done') return <p className="feedback-done" role="status">{t('fbThanks')}</p>

  return (
    <section className="feedback" aria-label={t('fbTitle')}>
      <h2>{t('fbTitle')}</h2>
      <p className="footnote">{t('fbNote')}</p>
      {QUESTIONS.map((q) => (
        <fieldset key={q}>
          <legend>{t(`fb_${q}`)}</legend>
          <div className="choice">
            {ANSWERS.map((a) => (
              <button type="button" key={a} className={values[q] === a ? 'on' : ''} aria-pressed={values[q] === a}
                onClick={() => setValues({ ...values, [q]: a })}>{t(`fb_${a}`)}</button>
            ))}
          </div>
        </fieldset>
      ))}
      <fieldset>
        <legend>{t('fb_language')}</legend>
        <div className="choice">
          {['bn', 'en', 'both'].map((a) => (
            <button type="button" key={a} className={values.preferred_lang === a ? 'on' : ''} aria-pressed={values.preferred_lang === a}
              onClick={() => setValues({ ...values, preferred_lang: a })}>{t(`fb_lang_${a}`)}</button>
          ))}
        </div>
      </fieldset>
      <label className="field">
        <span>{t('fbComment')}</span>
        <input value={comment} maxLength={200} onChange={(e) => setComment(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <button className="btn primary" disabled={!ready || state === 'sending'} onClick={send}>{t('fbSend')}</button>
    </section>
  )
}
