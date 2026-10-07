const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

function sessionId() {
  try {
    let id = localStorage.getItem('thamun-session')
    if (!id) {
      id = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`
      localStorage.setItem('thamun-session', id)
    }
    return id
  } catch {
    return 'shared'
  }
}

let token = null
let tokenless = false
let starting = null

function remembered() {
  try {
    return localStorage.getItem('thamun-token')
  } catch {
    return null
  }
}

function remember(value) {
  token = value
  try {
    if (value) localStorage.setItem('thamun-token', value)
    else localStorage.removeItem('thamun-token')
  } catch {
    return
  }
}

function startSession() {
  if (!starting) {
    starting = fetch(BASE + '/auth/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then(async (response) => {
        if (response.status === 404) {
          tokenless = true
          return null
        }
        if (!response.ok) throw new Error('The session could not be started.')
        const data = await response.json()
        remember(data.access_token)
        return data.access_token
      })
      .finally(() => {
        starting = null
      })
  }
  return starting
}

async function bearer() {
  if (tokenless) return null
  if (!token) token = remembered()
  return token || startSession()
}

async function request(path, options = {}, retried = false) {
  const headers = { 'Content-Type': 'application/json', 'X-Session': sessionId() }
  const current = await bearer()
  if (current) headers.Authorization = `Bearer ${current}`
  const response = await fetch(BASE + path, { ...options, headers })
  if (response.status === 401 && !retried) {
    remember(null)
    await startSession()
    return request(path, options, true)
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data && data.detail
    throw new Error(typeof detail === 'string' ? detail : 'The request could not be completed.')
  }
  return data
}

const get = (path, params = {}) => {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
  return request(query.toString() ? `${path}?${query}` : path)
}

const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) })

export const api = {
  base: BASE,
  health: () => get('/health'),
  customers: () => get('/customers'),
  home: (customer_id, lang) => get('/home', { customer_id, lang }),
  payees: (customer_id, lang) => get('/payees', { customer_id, lang }),
  script: (customer_id) => get('/demo/script', { customer_id }),
  check: (body) => post('/check', body),
  pay: (body) => post('/pay', body),
  label: (body) => post('/label', body),
  cashIn: (customer_id, amount) => post('/cashin', { customer_id, amount }),
  review: (customer_id, month, lang) => get('/review', { customer_id, month, lang }),
  goal: (customer_id, lang) => get('/goal', { customer_id, lang }),
  setGoal: (customer_id, target, months, lang) => post('/goal', { customer_id, target, months, lang }),
  saveToGoal: (customer_id, amount, lang) => post('/goal/save', { customer_id, amount, lang }),
  ask: (customer_id, question, lang) => post('/ask', { customer_id, question, lang }),
  reports: () => get('/reports'),
  reportOptions: (lang) => get('/reports/options', { lang }),
  checkNumber: (customer_id, number, lang) => get('/reports/check', { customer_id, number, lang }),
  report: (body) => post('/reports', body),
  reset: (customer_id) => post('/demo/reset', customer_id ? { customer_id } : {}),
  metrics: () => get('/metrics'),
  evidence: () => get('/evidence'),
  analytics: (scope) => get('/analytics', { scope }),
  monitoring: () => get('/monitoring'),
  feedback: (body) => post('/feedback', body),
  feedbackSummary: () => get('/feedback/summary'),
}
