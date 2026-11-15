import { api } from './api.js'

/** Server-side defaults, shared by the Settings form and the download form. */
export const prefs = $state({
  loaded: false,
  default_preset: {},
  default_template: '{artist}/{album}/{track:02d} - {title}',
  template_tokens: [],
  allow_write: false,
  has_cookies: false,
})

export async function loadPrefs() {
  const data = await api('/prefs')
  Object.assign(prefs, data, { loaded: true })
  return data
}

export async function savePrefs(payload) {
  const data = await api('/prefs', { method: 'PUT', body: payload })
  Object.assign(prefs, data, { loaded: true })
  return data
}
