/**
 * Download form state that survives tab switches (and reloads).
 *
 * The tab bar unmounts components, so keeping this in a component would reset
 * the URL and options every time the user looks at the queue.
 */
const KEY = 'ytdlweb:draft'

const BASE = {
  url: '',
  mode: 'video',
  quality: 'best',
  audioFormat: 'mp3',
  audioQuality: '0',
  playlistItems: '',
  outtmpl: '%(title)s [%(id)s].%(ext)s',
  embedThumb: true,
  embedMeta: true,
  subtitles: false,
  archive: true,
  sponsorblock: 'off',
  rateLimit: '',
}

function readSaved() {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

const saved = typeof localStorage === 'undefined' ? null : readSaved()
const restored = saved !== null

export const draft = $state({ ...BASE, ...(saved || {}) })

export function persistDraft() {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...draft }))
  } catch {
    /* private mode / quota: the in-memory draft still works */
  }
}

/** Apply saved server defaults, but never clobber a draft the user restored. */
export function applyDefaults(preset) {
  if (restored || !preset) return
  if (preset.mode) draft.mode = preset.mode
  if (preset.quality) draft.quality = preset.quality
  if (preset.audio_format) draft.audioFormat = preset.audio_format
  if (preset.audio_quality !== undefined) draft.audioQuality = String(preset.audio_quality)
  if (preset.outtmpl) draft.outtmpl = preset.outtmpl
  if (preset.sponsorblock) draft.sponsorblock = preset.sponsorblock
  if (preset.rate_limit !== undefined) draft.rateLimit = preset.rate_limit
  if (preset.embed_thumbnail !== undefined) draft.embedThumb = Boolean(preset.embed_thumbnail)
  if (preset.embed_metadata !== undefined) draft.embedMeta = Boolean(preset.embed_metadata)
  if (preset.subtitles !== undefined) draft.subtitles = Boolean(preset.subtitles)
  if (preset.archive !== undefined) draft.archive = Boolean(preset.archive)
}

export function presetFromDraft(extra = {}) {
  return {
    mode: draft.mode,
    quality: draft.quality,
    audio_format: draft.audioFormat,
    audio_quality: draft.audioQuality,
    playlist_items: draft.playlistItems,
    outtmpl: draft.outtmpl,
    embed_metadata: draft.embedMeta,
    embed_thumbnail: draft.embedThumb,
    subtitles: draft.subtitles,
    embed_subs: draft.subtitles,
    archive: draft.archive,
    sponsorblock: draft.sponsorblock,
    rate_limit: draft.rateLimit,
    ...extra,
  }
}
