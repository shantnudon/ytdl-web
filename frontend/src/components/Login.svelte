<script>
  import { api } from '../lib/api.js'

  let { onSuccess } = $props()

  let password = $state('')
  let error = $state('')
  let busy = $state(false)

  async function submit(event) {
    event.preventDefault()
    busy = true
    error = ''
    try {
      await api('/auth/login', { method: 'POST', body: { password } })
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
      This instance is password protected. Enter the password set with
      <code>APP_PASSWORD</code>.
    </p>

    <label class="field">
      <span>Password</span>
      <input type="password" bind:value={password} autocomplete="current-password" />
    </label>

    {#if error}
      <div class="notice error">{error}</div>
    {/if}

    <button class="primary" style="width:100%;margin-top:14px" disabled={busy || !password}>
      {busy ? 'Checking…' : 'Unlock'}
    </button>
  </form>
</div>
