<script>
  import { api } from '../lib/api.js'

  let { onSuccess } = $props()

  let token = $state('')
  let error = $state('')
  let busy = $state(false)

  async function submit(event) {
    event.preventDefault()
    busy = true
    error = ''
    try {
      await api('/auth/login', { method: 'POST', body: { token } })
      onSuccess?.()
    } catch (problem) {
      error = problem.message
    } finally {
      busy = false
    }
  }
</script>

<div class="login-wrap">
  <form class="login-card" onsubmit={submit}>
    <div class="brand" style="margin-bottom:6px">ytdl<span>web</span></div>
    <p class="muted small" style="margin-top:0">
      This instance requires an access token. It is the value of <code>APP_TOKEN</code>.
    </p>

    <label class="field">
      <span>Access token</span>
      <input type="password" bind:value={token} autocomplete="current-password" />
    </label>

    {#if error}
      <div class="notice error">{error}</div>
    {/if}

    <button class="primary" style="width:100%;margin-top:14px" disabled={busy || !token}>
      {busy ? 'Checking…' : 'Unlock'}
    </button>
  </form>
</div>
