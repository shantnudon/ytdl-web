<script>
  import { onMount } from 'svelte'
  import { api } from './lib/api.js'
  import { loadPrefs } from './lib/prefs.svelte.js'
  import { applyDefaults } from './lib/draft.svelte.js'
  import SubmitForm from './components/SubmitForm.svelte'
  import JobList from './components/JobList.svelte'
  import Library from './components/Library.svelte'
  import SettingsPanel from './components/SettingsPanel.svelte'
  import Login from './components/Login.svelte'

  let tab = $state('download')
  let jobs = $state([])
  let system = $state(null)
  let authRequired = $state(false)
  let authenticated = $state(true)
  let ready = $state(false)
  let connected = $state(false)
  let streamError = $state(false)
  let toast = $state('')
  let toastTimer

  async function bootstrap() {
    try {
      const status = await api('/auth/status')
      authRequired = status.auth_required
      authenticated = status.authenticated
      if (!status.authenticated) return
      try {
        const data = await loadPrefs()
        applyDefaults(data.default_preset)
      } catch {
        /* defaults are optional */
      }
      await refresh()
    } catch (error) {
      notify(`Startup failed: ${error.message}`)
    } finally {
      ready = true
    }
  }

  async function refresh() {
    try {
      const [list, info] = await Promise.all([api('/jobs'), api('/system')])
      jobs = list.items
      system = info
    } catch (error) {
      notify(error.message)
    }
  }

  function notify(text) {
    toast = text
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => (toast = ''), 4000)
  }

  function upsert(job) {
    jobs = jobs.some((item) => item.id === job.id)
      ? jobs.map((item) => (item.id === job.id ? { ...item, ...job } : item))
      : [job, ...jobs]
  }

  async function onLogin() {
    authenticated = true
    await bootstrap()
  }

  onMount(() => {
    bootstrap()
    const onUnauthorized = () => {
      authenticated = false
      connected = false
    }
    window.addEventListener('ytdlweb:unauthorized', onUnauthorized)
    return () => {
      window.removeEventListener('ytdlweb:unauthorized', onUnauthorized)
      clearTimeout(toastTimer)
    }
  })

  // Only open the stream once we are authenticated: an EventSource that gets a
  // 401 at page load does not retry, which is why the queue looked frozen until
  // a reload. Tying it to `authenticated` re-creates it after login.
  $effect(() => {
    if (!ready || !authenticated) return
    const source = new EventSource('/api/events')
    source.onopen = () => {
      connected = true
      streamError = false
    }
    source.onmessage = (event) => {
      let payload
      try {
        payload = JSON.parse(event.data)
      } catch {
        return
      }
      if (payload.type === 'job.updated') upsert(payload.data)
      if (payload.type === 'library.scanned') {
        notify(`Library: ${payload.data.added} added, ${payload.data.updated} updated`)
      }
    }
    source.onerror = () => {
      connected = false
      streamError = true
    }
    return () => source.close()
  })

  // Safety net for buffering proxies or a dropped stream.
  $effect(() => {
    if (!ready || !authenticated || connected) return
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  })
</script>

{#if !ready}
  <div class="empty">loading…</div>
{:else if authRequired && !authenticated}
  <Login onSuccess={onLogin} />
{:else}
  <div class="shell">
    <header class="top">
      <div class="brand">ytdl<span>web</span></div>
      {#if system?.ytdlp}
        <span class="badge">yt-dlp {system.ytdlp}</span>
      {/if}
      {#if streamError}
        <span class="badge interrupted" title="Live updates paused, falling back to polling">
          reconnecting
        </span>
      {/if}
      <nav class="tabs">
        <button class:active={tab === 'download'} onclick={() => (tab = 'download')}>Download</button>
        <button class:active={tab === 'queue'} onclick={() => (tab = 'queue')}>
          Queue{#if jobs.length}<span class="muted"> · {jobs.length}</span>{/if}
        </button>
        <button class:active={tab === 'library'} onclick={() => (tab = 'library')}>Library</button>
        <button class:active={tab === 'settings'} onclick={() => (tab = 'settings')}>Settings</button>
      </nav>
    </header>

    {#if tab === 'download'}
      <SubmitForm {notify} onQueued={upsert} />
    {:else if tab === 'queue'}
      <JobList {jobs} onChanged={refresh} {notify} />
    {:else if tab === 'library'}
      <Library {notify} allowWrite={system?.allow_write ?? false} />
    {:else}
      <SettingsPanel {system} {notify} onRefresh={refresh} />
    {/if}
  </div>
{/if}

{#if toast}
  <div class="toast">{toast}</div>
{/if}
