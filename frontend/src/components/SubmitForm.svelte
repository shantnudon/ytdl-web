<script>
  import { api } from '../lib/api.js'
  import { fmtDuration } from '../lib/format.js'
  import { draft, persistDraft, presetFromDraft } from '../lib/draft.svelte.js'
  import Skeleton from './Skeleton.svelte'

  let { notify, onQueued } = $props()

  let info = $state(null)
  let busy = $state(false)
  let probing = $state(false)
  let error = $state('')
  let advanced = $state(false)
  let duplicate = $state(null)
  let probedFor = ''

  let urls = $derived(draft.url.split(/\s+/).filter((value) => value.length > 1))

  $effect(() => {
    persistDraft()
  })

  // Fetch metadata as soon as a single URL is typed/pasted, so the queue can
  // show a real title even before the download starts.
  $effect(() => {
    const target = urls.length === 1 ? urls[0] : ''
    if (!target) {
      info = null
      probedFor = ''
      return
    }
    if (target === probedFor) return
    const timer = setTimeout(() => probe(target), 700)
    return () => clearTimeout(timer)
  })

  async function probe(target) {
    if (!target) return
    probing = true
    try {
      info = await api('/probe', { method: 'POST', body: { url: target } })
      probedFor = target
    } catch (problem) {
      info = null
      error = problem.message
    } finally {
      probing = false
    }
  }

  async function download(force = false) {
    if (!urls.length) return
    busy = true
    error = ''
    duplicate = null
    let queued = 0

    try {
      for (const target of urls) {
        const body = { url: target, preset: presetFromDraft(force ? { force: true } : {}) }
        if (urls.length === 1 && info?.title) body.title = info.title
        try {
          const job = await api('/jobs', { method: 'POST', body })
          onQueued?.(job)
          queued += 1
        } catch (problem) {
          if (problem.status === 409) {
            duplicate = { url: target, existing: problem.payload?.detail?.existing || null }
            break
          }
          throw problem
        }
      }
      if (queued > 0) {
        notify?.(`Queued ${queued} job${queued === 1 ? '' : 's'}`)
        draft.url = ''
        info = null
        probedFor = ''
      }
    } catch (problem) {
      error = problem.message
    } finally {
      busy = false
    }
  }
</script>

<div class="panel">
  <h2>New download</h2>
  <p class="hint">One URL per line. Playlists are supported — metadata is fetched automatically.</p>

  <label class="field">
    <span>URLs</span>
    <textarea rows="3" bind:value={draft.url} placeholder="https://www.youtube.com/watch?v=…"></textarea>
  </label>

  <div class="row">
    <label class="field grow">
      <span>Mode</span>
      <select bind:value={draft.mode}>
        <option value="video">Video</option>
        <option value="audio">Audio only</option>
      </select>
    </label>

    {#if draft.mode === 'video'}
      <label class="field grow">
        <span>Max resolution</span>
        <select bind:value={draft.quality}>
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
        <select bind:value={draft.audioFormat}>
          <option value="mp3">MP3</option>
          <option value="m4a">M4A</option>
          <option value="opus">Opus</option>
          <option value="flac">FLAC</option>
        </select>
      </label>
      <label class="field grow">
        <span>Quality</span>
        <select bind:value={draft.audioQuality}>
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
    <label><input type="checkbox" bind:checked={draft.embedMeta} /> Embed metadata</label>
    <label><input type="checkbox" bind:checked={draft.embedThumb} /> Embed thumbnail</label>
    <label><input type="checkbox" bind:checked={draft.subtitles} /> Subtitles</label>
    <label><input type="checkbox" bind:checked={draft.archive} /> Skip already downloaded</label>
    <label>
      SponsorBlock
      <select bind:value={draft.sponsorblock} style="width:auto">
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
        <input type="text" bind:value={draft.playlistItems} placeholder="all" />
      </label>
      <label class="field grow">
        <span>Filename template</span>
        <input type="text" bind:value={draft.outtmpl} />
      </label>
      <label class="field grow">
        <span>Rate limit (e.g. 5M)</span>
        <input type="text" bind:value={draft.rateLimit} placeholder="unlimited" />
      </label>
    </div>
  {/if}

  <div class="row" style="margin-top:6px">
    <button class="primary" disabled={busy || !urls.length} onclick={() => download()}>
      {busy ? 'Working…' : `Download${urls.length > 1 ? ` (${urls.length})` : ''}`}
    </button>
    <button
      class="ghost"
      disabled={busy || probing || urls.length !== 1}
      onclick={() => probe(urls[0])}
    >
      {probing ? 'Fetching…' : 'Refresh metadata'}
    </button>
    <span class="muted small">
      {#if probing}
        Fetching metadata…
      {:else}
        Format choice is final once the job starts.
      {/if}
    </span>
  </div>

  {#if error}
    <div class="notice error">{error}</div>
  {/if}

  {#if probing && !info}
    <div class="notice" aria-busy="true">
      <div style="display:flex;gap:12px;align-items:flex-start">
        <Skeleton width="132px" height="74px" radius="8px" />
        <div style="flex:1">
          <Skeleton width="72%" height="15px" />
          <div style="height:8px"></div>
          <Skeleton width="46%" height="11px" />
          <div style="height:6px"></div>
          <Skeleton width="38%" height="11px" />
        </div>
      </div>
    </div>
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

{#if duplicate}
  <div class="overlay" role="presentation">
    <div class="dialog">
      <h3>Already downloaded</h3>
      <p class="muted">
        This URL has a finished download{#if duplicate.existing?.title}
          — <strong>{duplicate.existing.title}</strong>{/if}. Downloading it again creates a
        new file, which is what you want when switching format or quality.
      </p>
      <div class="actions">
        <button class="ghost" onclick={() => (duplicate = null)}>Cancel</button>
        <button class="primary" disabled={busy} onclick={() => download(true)}>
          Download anyway
        </button>
      </div>
    </div>
  </div>
{/if}
