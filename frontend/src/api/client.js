const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const TOKEN_KEY = 'trend-radar-token'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }

  get isUnauthorized() {
    return this.status === 401
  }
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

async function request(path, { method = 'GET', body, isFormData = false } = {}) {
  const headers = {}
  const token = getToken()

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  if (body && !isFormData) {
    headers['Content-Type'] = 'application/json'
  }

  let response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: isFormData ? body : body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('Cannot reach the server. Is the backend running?', 0)
  }

  if (response.status === 204) {
    return null
  }

  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    throw new ApiError(extractMessage(payload, response.status), response.status)
  }

  return payload
}

// FastAPI returns `detail` as a string, or as a list for validation errors.
function extractMessage(payload, status) {
  const detail = payload?.detail

  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join('; ')
  }
  return `Request failed with status ${status}`
}

export const api = {
  login: (username, password) =>
    request('/api/auth/login', { method: 'POST', body: { username, password } }),

  me: () => request('/api/auth/me'),

  health: () => request('/api/health'),

  listProducts: ({ limit = 100, offset = 0 } = {}) =>
    request(`/api/products?limit=${limit}&offset=${offset}`),

  listPastProducts: ({ limit = 100, offset = 0 } = {}) =>
    request(`/api/sales-boost?limit=${limit}&offset=${offset}`),

  createPastProduct: (payload) =>
    request('/api/sales-boost', { method: 'POST', body: payload }),

  importPastProductsCsv: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/api/sales-boost/import-csv', {
      method: 'POST',
      body: form,
      isFormData: true,
    })
  },

  startRun: () => request('/api/scrape-runs', { method: 'POST' }),

  latestRun: () => request('/api/scrape-runs/latest'),

  listRuns: ({ limit = 10 } = {}) => request(`/api/scrape-runs?limit=${limit}`),
}
