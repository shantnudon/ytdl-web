<script>
  import { api } from '../lib/api.js'

  let { system = null, notify, onRefresh } = $props()

  let busy = $state(false)
  let error = $state('')

  async function uploadCookies(event) {
    const file = event.target.files?.[0]
    if (!file) return
    const body = new FormData()
    body.append('file', file)
    busy = true
    try {
      await api('/prefs/cookies', { method: 'POST', form: body })
      notify?.('Cookies uploaded')
      onRefresh?.()
    } catch (problem) {
      error = problem.message
    } finally {
      busy = false
      event.target.value = ''
    }
  }

  async function clearCookies() {
    try {
      await api('/prefs/cookies', { method: 'DELETE' })
      notify?.('Cookies removed')
      onRefresh?.()
    } catch (problem) {
      error = problem.message
    }
  }

  async function updateExtractors() {
    busy = true
    error = ''
    try {
      const result = await api('/prefs/update-extractors', { method: 'POST' })
      notify?.(`Extractors updated to ${result.version} — restart to load them`)
    } catch (problem) {
      error = problem.message
    } finally {
      busy = false
    }
  }

  async function logout() {
    try {
      await api('/auth/logout', { method: 'POST' })
    } finally {
      window.location.reload()
    }
  }
</script>

<div class="panel">
  <h2>Runtime</h2>
  <p class="hint">Values are read at startup from environment variables or <code>.env</code>.</p>

  {#if system}
    <div class="grid-2">
      <div><div class="muted small">ytdlweb</div><div class="mono">{system.version}</div></div>
      <div><div class="muted small">yt-dlp</div><div class="mono">{system.ytdlp}</div></div>
      <div><div class="muted small">Python</div><div class="mono">{system.python}</div></div>
      <div>
        <div class="muted small">ffmpeg</div>
        <div class="mono">{system.ffmpeg || 'not found — merging and audio extraction will fail'}</div>
      </div>
      <div><div class="muted small">Downloads</div><div class="mono">{system.dirs.downloads}</div></div>
      <div><div class="muted small">Library</div><div class="mono">{system.dirs.library}</div></div>
      <div><div class="muted small">Config</div><div class="mono">{system.dirs.config}</div></div>
      <div>
        <div class="muted small">Extractor plugin</div>
        <div class="mono">{system.plugin_override ? 'active (override)' : 'bundled'}</div>
      </div>
      <div><div class="muted small">Library writes</div><div class="mono">{system.allow_write ? 'enabled' : 'disabled'}</div></div>
      <div><div class="muted small">Auth</div><div class="mono">{system.auth_required ? 'token required' : 'open (localhost)'}</div></div>
    </div>
  {/if}

  {#if error}
    <div class="notice error">{error}</div>
  {/if}
</div>

<div class="panel">
  <h2>Content access</h2>
  <p class="hint">
    A Netscape-format <code>cookies.txt</code> lets yt-dlp reach age-restricted or member-only
    videos. Browser cookie import does not work inside a container, so upload the file instead.
  </p>
  <div class="row">
    <label class="field grow" style="margin-bottom:0">
      <span>cookies.txt</span>
      <input type="file" accept=".txt" onchange={uploadCookies} disabled={busy} />
    </label>
    <button class="ghost" onclick={clearCookies}>Remove cookies</button>
  </div>
</div>

<div class="panel">
  <h2>Maintenance</h2>
  <p class="hint">
    yt-dlp is bundled, so new extractor fixes ship with a release. You can also pull the latest
    pure-python wheel into the plugin directory and restart — useful for a frozen single-file build.
  </p>
  <div class="row">
    <button class="ghost" disabled={busy} onclick={updateExtractors}>
      {busy ? 'Working…' : 'Update extractors from PyPI'}
    </button>
    <button class="ghost" onclick={onRefresh}>Refresh info</button>
    {#if system?.auth_required}
      <button class="danger" onclick={logout}>Log out</button>
    {/if}
  </div>
</div>
