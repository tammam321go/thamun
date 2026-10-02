import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { day } from './format'
import { translator } from './i18n'
import DemoGuide from './components/DemoGuide'
import Icon from './components/Icon'
import Inspector from './components/Inspector'
import Ask from './screens/Ask'
import Goals from './screens/Goals'
import Home from './screens/Home'
import Pay from './screens/Pay'
import Review from './screens/Review'

const TABS = ['home', 'pay', 'review', 'goals', 'ask']

export default function App() {
  const [status, setStatus] = useState('loading')
  const [boot, setBoot] = useState(0)
  const [customers, setCustomers] = useState([])
  const [customerId, setCustomerId] = useState('D0001')
  const [lang, setLang] = useState('en')
  const [tab, setTab] = useState('home')
  const [home, setHome] = useState(null)
  const [version, setVersion] = useState(0)
  const [resets, setResets] = useState(0)
  const [preset, setPreset] = useState(null)
  const [lastCheck, setLastCheck] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [panel, setPanel] = useState(null)
  const t = useMemo(() => translator(lang), [lang])

  useEffect(() => {
    let stopped = false
    let timer = null
    let tries = 0
    const attempt = () => {
      api.customers()
        .then((list) => {
          if (stopped) return
          setCustomers(list)
          setStatus('ready')
          api.metrics().then((m) => !stopped && setMetrics(m)).catch(() => {})
        })
        .catch(() => {
          if (stopped) return
          tries += 1
          if (tries > 22) setStatus('error')
          else timer = setTimeout(attempt, 4000)
        })
    }
    attempt()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [boot])

  useEffect(() => {
    if (status !== 'ready') return undefined
    let stopped = false
    api.home(customerId, lang).then((data) => !stopped && setHome(data)).catch(() => {})
    return () => {
      stopped = true
    }
  }, [status, customerId, lang, version])

  const refresh = useCallback(() => setVersion((v) => v + 1), [])

  const switchCustomer = (id) => {
    const next = customers.find((c) => c.customer_id === id)
    setCustomerId(id)
    setHome(null)
    setLastCheck(null)
    setPreset(null)
    setTab('home')
    if (next) setLang(next.language)
  }

  const resetDemo = async () => {
    await api.reset().catch(() => {})
    setLastCheck(null)
    setPreset(null)
    setTab('home')
    setResets((r) => r + 1)
    refresh()
  }

  const runScenario = (scenario) => {
    setPreset({ ...scenario, nonce: Date.now() })
    setTab('pay')
    setPanel(null)
  }

  const go = (name) => {
    setTab(name)
    setPanel(null)
  }

  if (status !== 'ready') {
    return (
      <div className="boot">
        <div className="boot-mark">থামুন</div>
        <p>{status === 'loading' ? t('waking') : t('failed')}</p>
        {status === 'loading' ? <div className="spinner" aria-hidden="true" /> : (
          <button className="btn primary" onClick={() => { setStatus('loading'); setBoot((b) => b + 1) }}>{t('retry')}</button>
        )}
        <p className="boot-api">{api.base}</p>
      </div>
    )
  }

  const customer = customers.find((c) => c.customer_id === customerId)

  return (
    <div className="stage">
      <aside className={`side ${panel === 'guide' ? 'open' : ''}`}>
        <DemoGuide customer={customer} customerId={customerId} version={version + resets} onRun={runScenario} onGo={go}
          onReset={resetDemo} onClose={() => setPanel(null)} />
      </aside>

      <main className="phone-wrap">
        <div className="phone" lang={lang}>
          <header className="topbar">
            <div className="brand">
              <span className="brand-mark" aria-hidden="true"><i /><i /></span>
              <span className="brand-name">Thamun</span>
            </div>
            <select className="who" value={customerId} onChange={(e) => switchCustomer(e.target.value)} aria-label="Demo customer">
              {customers.map((c) => <option key={c.customer_id} value={c.customer_id}>{c.name}</option>)}
            </select>
            <button className="lang" onClick={() => setLang(lang === 'en' ? 'bn' : 'en')} aria-label="Switch language">
              {lang === 'en' ? 'বাংলা' : 'EN'}
            </button>
          </header>
          <div className="notice">{t('demoBanner')} {home ? `${t('today')}: ${day(home.now, lang)}` : ''}</div>

          <div className="screen">
            {tab === 'home' && <Home home={home} t={t} lang={lang} customerId={customerId}
              onPay={(type) => { setPreset({ type, blank: true, nonce: Date.now() }); setTab('pay') }} onChanged={refresh} />}
            {tab === 'pay' && <Pay key={`${customerId}-${resets}`} customerId={customerId} lang={lang} t={t} home={home} preset={preset}
              onPresetUsed={() => setPreset(null)} onCheck={setLastCheck} onChanged={refresh} onHome={() => setTab('home')} />}
            {tab === 'review' && <Review customerId={customerId} lang={lang} t={t} version={version} />}
            {tab === 'goals' && <Goals customerId={customerId} lang={lang} t={t} version={version} onChanged={refresh} />}
            {tab === 'ask' && <Ask key={customerId} customerId={customerId} lang={lang} t={t} />}
          </div>

          <div className="mobile-switch">
            <button onClick={() => setPanel('guide')}>Demo guide</button>
            <button onClick={() => setPanel('why')}>Why it decided{lastCheck && lastCheck.decision !== 'silent' ? ' •' : ''}</button>
          </div>

          <nav className="tabs" aria-label="Sections">
            {TABS.map((name) => (
              <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)} aria-current={tab === name ? 'page' : undefined}>
                <Icon name={name} />
                <span>{t(name)}</span>
              </button>
            ))}
          </nav>
        </div>
      </main>

      <aside className={`side ${panel === 'why' ? 'open' : ''}`}>
        <Inspector check={lastCheck} metrics={metrics} onClose={() => setPanel(null)} />
      </aside>
    </div>
  )
}
