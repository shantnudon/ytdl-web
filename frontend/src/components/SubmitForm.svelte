<script>
  import { api } from '../lib/api.js'
  import { fmtDuration } from '../lib/format.js'

  let { notify, onQueued } = $props()

  let url = $state('')
  let mode = $state('video')
  let quality = $state('best')
  let audioFormat = $state('mp3')
  let audioQuality = $state('0')
  let playlistItems = $state('')
  let outtmpl = $state('%(title)s [%(id)s].%(ext)s')
  let embedThumb = $state(true)
  let embedMeta = $state(true)
  let subtitles = $state(false)
  let archive = $state(true)
  let sponsorblock = $state('off')
  let rateLimit = $state('')
  let advanced = $state(false)
  let info = $state(null)
  let busy = $state(false)
  let error = $state('')

  let urls = $derived(url.split(/\s+/).filter((value) => value.length > 1))

  function preset() {
    return {
      mode,
      quality,
      audio_format: audioFormat,
      audio_quality: audioQuality,
      playlist_items: playlistItems,
      outtmpl,
      embed_thumbnail: embedThumb,
      embed_metadata: embedMeta,
      subtitles,
      embed_subs: subtitles,
      archive,
      sponsorblock,
      rate_limit: rateLimit,
    }
  }

  async function probe() {
    if (!urls.length) return
    busy = true
    error = ''
    info = null
    try {
      info = await api('/probe', { method: 'POST', body: { url: urls[0] } })
    } catch (problem) {
      error = problem.message
    } finally {
      busy = false
    }
  }

  async function download() {
    if (!urls.length) return
    busy = true
    error = ''
    let queued = 0
    try {
      for (const target of urls) {
        const job = await api('/jobs', { method: 'POST', body: { url: target, preset: preset() } })
        onQueued?.(job)
        queued += 1
      }
      notify?.(`Queued ${queued} job${queued === 1 ? '' : 's'}`)
      url = ''
      info = null
    } catch (problem) {
      error = problem.message
    } finally {
      busy = false
    }
  }
</script>

<div class="panel">
  <h2>New download</h2>
  <p class="hint">One URL per line. Playlists are supported — probe first to inspect them.</p>

  <label class="field">
    <span>URLs</span>
    <textarea rows="3" bind:value={url} placeholder="https://www.youtube.com/watch?v=…"></textarea>
  </label>

  <div class="row">
    <label class="field grow">
      <span>Mode</span>
      <select bind:value={mode}>
        <option value="video">Video</option>
        <option value="audio">Audio only</option>
      </select>
    </label>

    {#if mode === 'video'}
      <label class="field grow">
        <span>Max resolution</span>
        <select bind:value={quality}>
          <option value="best">Best available</option>
          <option value="2160">2160p (4K)</option>
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
        <select bind:value={audioFormat}>
          <option value="mp3">MP3</option>
          <option value="m4a">M4A</option>
          <option value="opus">Opus</option>
          <option value="flac">FLAC</option>
        </select>
      </label>
      <label class="field grow">
        <span>Quality</span>
        <select bind:value={audioQuality}>
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
    <label><input type="checkbox" bind:checked={embedMeta} /> Embed metadata</label>
    <label><input type="checkbox" bind:checked={embedThumb} /> Embed thumbnail</label>
    <label><input type="checkbox" bind:checked={subtitles} /> Subtitles</label>
    <label><input type="checkbox" bind:checked={archive} /> Skip already downloaded</label>
    <label>
      SponsorBlock
      <select bind:value={sponsorblock} style="width:auto">
        <option value="off">off</option>
        <option value="mark">mark</option>
        <option value="remove">remove</option>
      </select>
    </label>
  </div>

  <button class="ghost tiny" onclick={() => (advanced = !advanced)}>
    {advanced ? 'Hide advanced' : 'Advanced options'}
  </button>

  {#if advanced}
    <div class="row" style="margin-top:12px">
      <label class="field grow">
        <span>Playlist items (e.g. 1-5,8)</span>
        <input type="text" bind:value={playlistItems} placeholder="all" />
      </label>
      <label class="field grow">
        <span>Filename template</span>
        <input type="text" bind:value={outtmpl} />
      </label>
      <label class="field grow">
        <span>Rate limit (e.g. 5M)</span>
        <input type="text" bind:value={rateLimit} placeholder="unlimited" />
      </label>
    </div>
  {/if}

  <div class="row" style="margin-top:6px">
    <button class="primary" disabled={busy || !urls.length} onclick={download}>
      {busy ? 'Working…' : `Download${urls.length > 1 ? ` (${urls.length})` : ''}`}
    </button>
    <button class="ghost" disabled={busy || !urls.length} onclick={probe}>Probe metadata</button>
    <span class="muted small">Yt-dlp handles the format selection; presets just cap resolution.</span>
  </div>

  {#if error}
    <div class="notice error">{error}</div>
  {/if}

  {#if info}
    <div class="notice">
      <div style="display:flex;gap:12px;align-items:flex-start">
        {#if info.thumbnail}
          <img src={info.thumbnail} alt="" style="width:132px;border-radius:8px" />
        {/if}
        <div>
          <div style="font-weight:600">{info.title}</div>
          <div class="muted small">
            {info.uploader || info.type}
            {#if info.duration}· {fmtDuration(info.duration)}{/if}
            {#if info.type === 'playlist'}· {info.entry_count} entries{/if}
          </div>
          {#if info.type === 'playlist'}
            <div class="mono small muted" style="margin-top:8px">
              {#each info.entries.slice(0, 6) as entry}
                <div>· {entry.title}</div>
              {/each}
              {#if info.entries.length > 6}
                <div>· … {info.entries.length - 6} more</div>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>
