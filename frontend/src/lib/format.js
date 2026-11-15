export function fmtBytes(value) {
  if (!value || value <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let index = 0
  let size = value
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[index]}`
}

export function fmtSpeed(value) {
  if (!value) return ''
  return `${fmtBytes(value)}/s`
}

export function fmtEta(seconds) {
  if (seconds === null || seconds === undefined) return ''
  if (seconds <= 0) return ''
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  if (minutes < 60) return `${minutes}m ${rest}s`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

export function fmtDuration(seconds) {
  if (!seconds || seconds <= 0) return '—'
  const total = Math.round(seconds)
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

export function shortPath(path) {
  if (!path) return ''
  const parts = path.split('/')
  return parts.slice(-2).join('/')
}
