// Management and token APIs share the Flask origin; no browser database secrets.
export async function api(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !path.startsWith('/public/')) {
    const auth = await api('/auth/session')
    if (auth.csrf_token) headers['X-CSRF-Token'] = auth.csrf_token
  }
  let response
  try {
    response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', headers })
  } catch {
    throw new Error('Cannot reach the app. Check your connection and try again.')
  }
  const data = await response.json().catch(() => null)
  if (!response.ok || !data) {
    if (response.status === 401 && !path.startsWith('/public/')) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`)
    }
    const error = new Error(data?.error?.message || 'The server could not complete this request. Please try again.')
    error.code = data?.error?.code
    throw error
  }
  return data
}

export const post = (path, data = {}) => api(path, { method: 'POST', body: JSON.stringify(data) })
