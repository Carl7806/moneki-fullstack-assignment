const BASE = '/api'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.error || `请求失败 (HTTP ${res.status})`)
  }
  return res.json()
}

function buildQuery(params = {}) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v) qs.set(k, v)
  })
  const s = qs.toString()
  return s ? `?${s}` : ''
}

export const fetchSummary = (params) => get(`/dashboard/summary${buildQuery(params)}`)
export const fetchDaily = (params) => get(`/dashboard/daily${buildQuery(params)}`)
export const fetchTop10 = (params) => get(`/dashboard/top10${buildQuery(params)}`)
export const fetchAnomalies = (params) => get(`/dashboard/anomalies${buildQuery(params)}`)

export async function fetchChat(message, history) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `请求失败 (HTTP ${res.status})`)
  return data
}