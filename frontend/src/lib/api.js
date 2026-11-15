export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
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
    throw new ApiError(`network error: ${error.message}`, 0)
  }

  const payload = parse(await response.text())

  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent('ytdlweb:unauthorized'))
  }

  if (!response.ok) {
    const detail = payload?.detail
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || item).join(', ')
      : detail || response.statusText || 'request failed'
    throw new ApiError(message, response.status)
  }

  return payload
}
