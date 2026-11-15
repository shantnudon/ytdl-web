<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { fmtDuration } from '../lib/format.js'

  let { notify, allowWrite = false } = $props()

  let items = $state([])
  let total = $state(0)
  let query = $state('')
  let scanning = $state(false)
  let busy = $state(false)
  let error = $state('')
  let editing = $state(null)
  let form = $state({})
  let template = $state('{artist}/{album}/{track:02d} - {title}')
  let plan = $state(null)
  let selected = $state([])
  let searchTimer

  async function load() {
    try {
      const data = await api(`/library?q=${encodeURIComponent(query)}&limit=300`)
      items = data.items
      total = data.total
      error = ''
    } catch (problem) {
      error = problem.message
    }
  }

  onMount(async () => {
    try {
      const prefs = await api('/prefs')
      template = prefs.default_template
    } catch {
      /* prefs are optional */
    }
    await load()
  })

  function onSearch(event) {
    query = event.target.value
    clearTimeout(searchTimer)
    searchTimer = setTimeout(load, 250)
  }

  async function scan() {
    scanning = true
    error = ''
    try {
      const result = await api('/library/scan', { method: 'POST' })
      notify?.(`Scan: ${result.added} added, ${result.updated} updated, ${result.removed} removed`)
      await load()
    } catch (problem) {
      error = problem.message
    } finally {
      scanning = false
    }
  }

  function toggle(id) {
    selected = selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id]
  }

  function toggleAll() {
    selected = selected.length === items.length ? [] : items.map((item) => item.id)
  }

  function openEdit(track) {
    editing = track
    form = {
      title: track.title || '',
      artist: track.artist || '',
      album: track.album || '',
      albumartist: track.albumartist || '',
      year: track.year || '',
      track: track.track || '',
      disc: track.disc || '',
      genre: track.genre || '',
      comment: track.comment || '',
    }
  }

  async function saveTags() {
    busy = true
    error = ''
    try {
      await api(`/library/${editing.id}/tags`, { method: 'PATCH', body: form })
      notify?.('Tags saved')
      editing = null
      await load()
    } catch (problem) {
      error = problem.message
    } finally {
      busy = false
    }
  }

  async function uploadArt(event) {
    const file = event.target.files?.[0]
    if (!file || !editing) return
    const body = new FormData()
    body.append('file', file)
    try {
      await api(`/library/${editing.id}/art`, { method: 'PUT', form: body })
      notify?.('Cover art updated')
      await load()
    } catch (problem) {
      error = problem.message
    }
    event.target.value = ''
  }

  async function removeArt() {
    if (!editing) return
    try {
      await api(`/library/${editing.id}/art`, { method: 'DELETE' })
      notify?.('Cover art removed')
      await load()
    } catch (problem) {
      error = problem.message
    }
  }

  async function preview() {
    busy = true
    error = ''
    try {
      plan = await api('/library/rename/preview', {
        method: 'POST',
        body: { ids: selected, template },
      })
    } catch (problem) {
      error = problem.message
    } finally {
      busy = false
    }
  }

  async function apply() {
    busy = true
    error = ''
    try {
      const result = await api('/library/rename/apply', {
        method: 'POST',
        body: { ids: selected, template },
      })
      notify?.(`Moved ${result.moved}, skipped ${result.skipped.length}`)
      plan = null
      selected = []
      await load()
    } catch (problem) {
      error = problem.message
    } finally {
      busy = false
    }
  }

  async function undoRename() {
    try {
      const result = await api('/library/undo/rename', { method: 'POST' })
      notify?.(`Reverted ${result.reverted} rename(s)`)
      await load()
    } catch (problem) {
      error = problem.message
    }
  }

  async function undoTags() {
    try {
      await api('/library/undo/tags', { method: 'POST' })
      notify?.('Last tag edit reverted')
      await load()
    } catch (problem) {
      error = problem.message
    }
  }
</script>

<div class="panel">
  <h2>Library</h2>
  <p class="hint">
    Scans the mounted music directory. {total} track{total === 1 ? '' : 's'} indexed.
    {#if !allowWrite}
      Writes are disabled — start the server with <code>ALLOW_WRITE=true</code> to edit tags or rename files.
    {/if}
  </p>

  <div class="row">
    <label class="field grow" style="margin-bottom:0">
      <span>Search</span>
      <input type="text" value={query} oninput={onSearch} placeholder="artist, album, title, filename" />
    </label>
    <button class="ghost" disabled={scanning} onclick={scan}>
      {scanning ? 'Scanning…' : 'Rescan library'}
    </button>
  </div>

  {#if error}
    <div class="notice error">{error}</div>
  {/if}
</div>

{#if selected.length > 0}
  <div class="panel">
    <h2>Rename {selected.length} track{selected.length === 1 ? '' : 's'}</h2>
    <p class="hint">
      Preview first. Files that would collide, or that changed since the preview, are skipped.
    </p>

    <div class="row">
      <label class="field grow" style="margin-bottom:0">
        <span>Template</span>
        <input type="text" bind:value={template} />
      </label>
      <button class="ghost" disabled={busy || !allowWrite} onclick={preview}>Preview</button>
      <button class="primary" disabled={busy || !allowWrite || !plan} onclick={apply}>
        Apply {plan ? `(${plan.ok})` : ''}
      </button>
    </div>

    <div class="row" style="margin-top:10px">
      <button class="ghost tiny" onclick={() => (selected = [])}>Clear selection</button>
      <button class="ghost tiny" onclick={undoRename}>Undo last rename</button>
      <button class="ghost tiny" onclick={undoTags}>Undo last tag edit</button>
      <span class="muted small mono">
        tokens: {'{artist} {album} {title} {track:02d} {disc} {year} {ext}'}
      </span>
    </div>

    {#if plan}
      <table style="margin-top:12px">
        <thead>
          <tr><th>From</th><th>To</th><th style="width:120px">Status</th></tr>
        </thead>
        <tbody>
          {#each plan.items as item (item.id)}
            <tr>
              <td class="mono small">{item.src_rel}</td>
              <td class="mono small">{item.dst_rel}</td>
              <td>
                <span class={`badge ${item.status === 'ok' ? 'done' : 'interrupted'}`}>{item.status}</span>
                {#if item.reason}<div class="muted small">{item.reason}</div>{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
{/if}

<div class="panel">
  {#if items.length === 0}
    <div class="empty">
      No tracks yet. Mount your music directory at the library path, then hit “Rescan library”.
    </div>
  {:else}
    <table>
      <thead>
        <tr>
          <th style="width:34px"><input type="checkbox" checked={selected.length === items.length} onchange={toggleAll} /></th>
          <th>Title</th>
          <th>Artist</th>
          <th>Album</th>
          <th style="width:64px">Time</th>
          <th style="width:60px">Art</th>
          <th style="width:70px"></th>
        </tr>
      </thead>
      <tbody>
        {#each items as track (track.id)}
          <tr>
            <td>
              <input
                type="checkbox"
                checked={selected.includes(track.id)}
                onchange={() => toggle(track.id)}
              />
            </td>
            <td>
              <div>{track.title || track.filename}</div>
              <div class="muted small mono">{track.relpath}</div>
            </td>
            <td>{track.artist}</td>
            <td>{track.album}</td>
            <td class="muted small">{fmtDuration(track.duration)}</td>
            <td>{track.has_art ? '🖼' : '—'}</td>
            <td>
              <button class="ghost tiny" onclick={() => openEdit(track)}>Edit</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

{#if editing}
  <div class="overlay" role="presentation" onclick={(event) => event.target === event.currentTarget && (editing = null)}>
    <div class="dialog">
      <h3>{editing.filename}</h3>

      <div class="grid-2">
        <label class="field"><span>Title</span><input type="text" bind:value={form.title} /></label>
        <label class="field"><span>Artist</span><input type="text" bind:value={form.artist} /></label>
        <label class="field"><span>Album</span><input type="text" bind:value={form.album} /></label>
        <label class="field"><span>Album artist</span><input type="text" bind:value={form.albumartist} /></label>
        <label class="field"><span>Year</span><input type="text" bind:value={form.year} /></label>
        <label class="field"><span>Track</span><input type="text" bind:value={form.track} /></label>
        <label class="field"><span>Disc</span><input type="text" bind:value={form.disc} /></label>
        <label class="field"><span>Genre</span><input type="text" bind:value={form.genre} /></label>
      </div>

      <label class="field"><span>Comment</span><textarea rows="2" bind:value={form.comment}></textarea></label>

      <div class="row">
        <label class="field grow" style="margin-bottom:0">
          <span>Cover art</span>
          <input type="file" accept="image/*" onchange={uploadArt} />
        </label>
        <button class="ghost tiny" onclick={removeArt}>Remove art</button>
      </div>

      <div class="actions">
        <button class="ghost" onclick={() => (editing = null)}>Cancel</button>
        <button class="primary" disabled={busy || !allowWrite} onclick={saveTags}>Save tags</button>
      </div>
    </div>
  </div>
{/if}
