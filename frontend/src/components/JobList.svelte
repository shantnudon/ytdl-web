<script>
  import { api } from '../lib/api.js'
  import { fmtSpeed, fmtEta, shortPath } from '../lib/format.js'
  import Skeleton from './Skeleton.svelte'

  let { jobs = [], loading = false, onChanged, notify } = $props()

  async function act(job, action) {
    try {
      await api(`/jobs/${job.id}/${action}`, { method: 'POST' })
      notify?.(action === 'cancel' ? 'Canceling…' : 'Requeued')
      onChanged?.()
    } catch (error) {
      notify?.(error.message)
    }
  }

  async function remove(job) {
    try {
      await api(`/jobs/${job.id}`, { method: 'DELETE' })
      onChanged?.()
    } catch (error) {
      notify?.(error.message)
    }
  }

  const canCancel = (job) => ['queued', 'running', 'postprocessing'].includes(job.status)
  const canRetry = (job) => ['failed', 'canceled', 'interrupted', 'done'].includes(job.status)
</script>

<div class="panel">
  <h2>Queue</h2>
  <p class="hint">
    Live progress arrives over SSE. Jobs survive a restart and resume from partial files.
  </p>

  {#if loading}
    <table aria-busy="true">
      <thead>
        <tr>
          <th>Job</th>
          <th style="width:26%">Progress</th>
          <th style="width:110px">Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each [0, 1, 2] as row (row)}
          <tr class="skeleton-row">
            <td>
              <Skeleton width="62%" height="14px" />
              <div style="height:7px"></div>
              <Skeleton width="38%" height="11px" />
            </td>
            <td>
              <Skeleton height="7px" radius="999px" />
              <div style="height:8px"></div>
              <Skeleton width="52%" height="11px" />
            </td>
            <td><Skeleton width="66px" height="20px" radius="999px" /></td>
            <td>
              <Skeleton width="56px" height="24px" radius="6px" style="margin-left:auto" />
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {:else if jobs.length === 0}
    <div class="empty">No jobs yet — paste a URL in the Download tab.</div>
  {:else}
    <table>
      <thead>
        <tr>
          <th>Job</th>
          <th style="width:26%">Progress</th>
          <th style="width:110px">Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each jobs as job (job.id)}
          <tr>
            <td>
              <div>{job.title || job.url}</div>
              {#if job.outpath}
                <div class="muted small mono">{shortPath(job.outpath)}</div>
              {:else if job.title}
                <div class="muted small mono">{job.url}</div>
              {/if}
              {#if job.error}
                <div class="notice error small">{job.error}</div>
              {/if}
            </td>
            <td>
              <div class="bar"><i style={`width:${Math.min(100, job.progress || 0)}%`}></i></div>
              <div class="muted small">
                {Math.round(job.progress || 0)}%{#if job.speed} · {fmtSpeed(job.speed)}{/if}{#if job.eta}
                  · {fmtEta(job.eta)} left{/if}
              </div>
            </td>
            <td><span class={`badge ${job.status}`}>{job.status}</span></td>
            <td>
              <div class="row" style="gap:6px;justify-content:flex-end">
                {#if canCancel(job)}
                  <button class="ghost tiny" onclick={() => act(job, 'cancel')}>Cancel</button>
                {/if}
                {#if canRetry(job)}
                  <button class="ghost tiny" onclick={() => act(job, 'retry')}>Retry</button>
                {/if}
                <button class="danger tiny" onclick={() => remove(job)}>Remove</button>
              </div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
