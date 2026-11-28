<script>
  import { api } from '../lib/api.js'
  import { prefs, savePrefs } from '../lib/prefs.svelte.js'
  import Skeleton from './Skeleton.svelte'

  let { system = null, notify, onRefresh } = $props()

  let busy = $state(false)
  let saving = $state(false)
  let error = $state('')
  let synced = $state(false)

  let form = $state({
    mode: 'video',
    quality: 'best',
    audio_format: 'mp3',
    audio_quality: '0',
    embed_metadata: true,
    embed_thumbnail: true,
    subtitles: false,
    archive: true,
    sponsorblock: 'off',
    outtmpl: '%(title)s [%(id)s].%(ext)s',
    rate_limit: '',
  })
  let template = $state('{artist}/{album}/{track:02d} - {title}')

  $effect(() => {
    if (prefs.loaded && !synced) {
      form = { ...form, ...prefs.default_preset }
      template = prefs.default_template
      synced = true
    }
  })

  async function saveDefaults() {
    saving = true
    error = ''
    try {
      await savePrefs({ default_preset: form, default_template: template })
      notify?.('Defaults saved')
    } catch (problem) {
      error = problem.message
    } finally {
      saving = false
    }
  }

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
  <h2>Download defaults</h2>
  <p class="hint">
    Saved on the server, so every browser starts with the same preset. The
    download form remembers your last manual changes separately.
  </p>

  <div class="row">
    <label class="field grow">
      <span>Mode</span>
      <select bind:value={form.mode}>
        <option value="video">Video</option>
        <option value="audio">Audio only</option>
      </select>
    </label>

    {#if form.mode === 'video'}
      <label class="field grow">
        <span>Max resolution</span>
        <select bind:value={form.quality}>
          <option value="best">Best available</option>
          <option value="2160">2160p</option>
          <option value="1440">1440p</option>
          <option value="1080">1080p</option>
          <option value="720">720p</option>
          <option value="480">480p</option>
          <option value="360">360p</option>
        </select>
      </label>
    {:else}
      <label class="field grow">
        <span>Audio format</span>
        <select bind:value={form.audio_format}>
          <option value="mp3">MP3</option>
          <option value="m4a">M4A</option>
          <option value="opus">Opus</option>
          <option value="flac">FLAC</option>
        </select>
      </label>
      <label class="field grow">
        <span>Audio quality</span>
        <select bind:value={form.audio_quality}>
          <option value="0">Best (VBR)</option>
          <option value="320">320 kbps</option>
          <option value="256">256 kbps</option>
          <option value="192">192 kbps</option>
          <option value="128">128 kbps</option>
        </select>
      </label>
    {/if}
  </div>

  <div class="checks">
    <label><input type="checkbox" bind:checked={form.embed_metadata} /> Embed metadata</label>
    <label><input type="checkbox" bind:checked={form.embed_thumbnail} /> Embed thumbnail</label>
    <label><input type="checkbox" bind:checked={form.subtitles} /> Subtitles</label>
    <label><input type="checkbox" bind:checked={form.archive} /> Skip already downloaded</label>
    <label>
      SponsorBlock
      <select bind:value={form.sponsorblock} style="width:auto">
        <option value="off">off</option>
        <option value="mark">mark</option>
        <option value="remove">remove</option>
      </select>
    </label>
  </div>

  <div class="row">
    <label class="field grow">
      <span>Filename template</span>
      <input type="text" bind:value={form.outtmpl} />
    </label>
    <label class="field grow">
      <span>Rate limit</span>
      <input type="text" bind:value={form.rate_limit} placeholder="unlimited" />
    </label>
  </div>

  <label class="field">
    <span>Library rename template</span>
    <input type="text" bind:value={template} />
  </label>
  <p class="muted small" style="margin-top:-6px">
    tokens: {prefs.template_tokens.map((token) => `{${token}}`).join(' ')}
  </p>

  {#if error}
    <div class="notice error">{error}</div>
  {/if}

  <div class="row" style="margin-top:12px">
    <button class="primary" disabled={saving} onclick={saveDefaults}>
      {saving ? 'Saving…' : 'Save defaults'}
    </button>
  </div>
</div>

<div class="panel">
  <h2>Runtime</h2>
  <p class="hint">Read at startup from environment variables or <code>.env</code>.</p>

  {#if system}
    <div class="grid-2">
      <div><div class="muted small">ytdlweb</div><div class="mono">{system.version}</div></div>
      <div><div class="muted small">yt-dlp</div><div class="mono">{system.ytdlp}</div></div>
      <div><div class="muted small">Python</div><div class="mono">{system.python}</div></div>
      <div>
        <div class="muted small">ffmpeg</div>
        <div class="mono">{system.ffmpeg || 'not found — merging and audio extraction will fail'}</div>
      </div>
      <div>
        <div class="muted small">JS runtime</div>
        <div class="mono">{system.js_runtime?.runtimes?.join(', ') || 'none — YouTube will fail'}</div>
      </div>
      <div><div class="muted small">Downloads</div><div class="mono">{system.dirs.downloads}</div></div>
      <div><div class="muted small">Library</div><div class="mono">{system.dirs.library}</div></div>
      <div><div class="muted small">Config</div><div class="mono">{system.dirs.config}</div></div>
      <div>
        <div class="muted small">Extractor plugin</div>
        <div class="mono">{system.plugin_override ? 'active (override)' : 'bundled'}</div>
      </div>
      <div><div class="muted small">Library writes</div><div class="mono">{system.allow_write ? 'enabled' : 'disabled'}</div></div>
      <div><div class="muted small">Password</div><div class="mono">{system.auth_required ? 'required' : 'not set (open on localhost)'}</div></div>
    </div>
  {:else}
    <div class="grid-2" aria-busy="true">
      {#each [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] as row (row)}
        <div class="skeleton-stack">
          <Skeleton width="74px" height="11px" />
          <Skeleton width={`${45 + (row % 4) * 12}%`} height="13px" />
        </div>
      {/each}
    </div>
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
