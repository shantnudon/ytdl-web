export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

function parse(text) {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

function messageFrom(detail, fallback) {
  if (Array.isArray(detail)) return detail.map((item) => item.msg || item).join(', ')
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail)
  return detail || fallback || 'request failed'
}

/**
 * Thin fetch wrapper: always sends the CSRF header and surfaces API errors.
 * @param {string} path path after /api
 */
export async function api(path, { method = 'GET', body, form, headers = {} } = {}) {
  const options = { method, headers: { 'X-Requested-With': 'ytdlweb', ...headers } }

  if (form) {
    options.body = form
  } else if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(`/api${path}`, options)
  } catch (error) {
    throw new ApiError(`network error: ${error.message}`, 0, null)
  }

  const payload = parse(await response.text())

  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent('ytdlweb:unauthorized'))
  }

  if (!response.ok) {
    throw new ApiError(messageFrom(payload?.detail, response.statusText), response.status, payload)
  }

  return payload
}
