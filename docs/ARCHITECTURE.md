# Architecture

## Shape of the system

```
       ┌──────────────────────────────────────────────┐
       │ Svelte 5 SPA (built into app/static)         │
       │  Download · Queue · Library · Settings       │
       └───────────────┬──────────────────────────────┘
                       │  /api/* (JSON) + /api/events (SSE)
       ┌───────────────▼──────────────────────────────┐
       │ FastAPI (app/main.py)                        │
       │  auth middleware · security headers · SPA    │
       ├──────────────────────────────────────────────┤
       │ api/jobs  api/library  api/prefs  api/system │
       ├───────────────┬──────────────┬───────────────┤
       │ DownloadManager│ Library      │ SQLite        │
       │ (worker pool)  │ (tags/rename)│ (WAL)         │
       └───────┬────────┴──────┬───────┴───────────────┘
               │               │
     asyncio.to_thread    mutagen + os.replace
               │
      ┌────────▼─────────┐      ┌──────────────┐
      │ yt_dlp (library) │─────▶│ ffmpeg       │
      └────────┬─────────┘      └──────────────┘
               │
      progress hooks (worker thread)
               │  loop.call_soon_threadsafe
      ┌────────▼─────────┐
      │ Broker → SSE     │
      └──────────────────┘
```

## Why FastAPI + `yt_dlp` as a library

- The Python API exposes format objects, progress hooks, postprocessor
  configuration and typed errors. Shelling out to the CLI would mean parsing
  text.
- One process, one dependency tree, one image. No Python runtime to install on
  the host.
- The trade-off is packaging: a frozen binary is heavier than a Go equivalent
  and cannot update yt-dlp by itself. See [Packaging](#packaging).

## Concurrency model

`yt_dlp` is fully synchronous and blocking. The rules:

1. Downloads never run on the event loop. `DownloadManager._run` calls
   `asyncio.to_thread`, and a fixed pool of `MAX_CONCURRENT` worker tasks
   consumes the job queue.
2. Progress hooks fire **on the download thread**. They write to SQLite
   (thread-safe, guarded by a lock) and hand events to the `Broker`, which uses
   `loop.call_soon_threadsafe`. Nothing from a hook ever `await`s.
3. Progress frames are throttled to 4 per second per job. Without this, a
   fragment-heavy download floods SSE and the browser.
4. Cancellation is a `threading.Event` checked inside the hook; the hook raises
   `yt_dlp.utils.DownloadCancelled`, which is the only supported abort path.

## Job lifecycle

```
queued ──▶ running ──▶ postprocessing ──▶ done
   │           │
   │           ├──▶ failed      (extractor/download error, message stored)
   │           └──▶ canceled    (user cancel)
   └──▶ canceled               (cancel before a worker picked it up)

server restart: running/postprocessing ──▶ interrupted
```

On startup, `Database.mark_interrupted()` rewrites stale rows. Requeueing an
interrupted job resumes from the `.part` files yt-dlp left behind, because
`continuedl` is enabled.

## Download pipeline

1. `POST /api/jobs` validates the URL scheme (http/https only), normalises the
   preset through an allow-list (`app/core/options.py`), stores the job, and
   enqueues the id.
2. A worker builds yt-dlp options: output template, format selector,
   postprocessors (extract audio, embed metadata/thumbnail, subtitles,
   SponsorBlock), archive path, cookies, ffmpeg location, JS runtimes.
3. `YoutubeDL.extract_info(url, download=True)` runs in a thread.
4. Postprocessor hooks capture the final filepath (after the audio extraction
   and `MoveFiles` pass), so the API reports the real output file.
5. The job row is finalised and an SSE frame is published.

Presets are translated, never passed through: a client cannot inject arbitrary
yt-dlp options.

## Library pipeline

```
scan:     walk LIBRARY_DIR ─▶ reject symlinks escaping root
          ─▶ mutagen read (tags, duration, bitrate, cover)
          ─▶ upsert into tracks (id is stable across renames)

edit:     resolve_within(root, relpath) ─▶ probe before
          ─▶ copy to sibling temp ─▶ mutagen write ─▶ os.replace
          ─▶ op_log("tags", {before})

rename:   plan(template, tracks) ─▶ sanitise every component
          ─▶ detect duplicates + existing targets + escaping paths
          ─▶ preview in UI ─▶ apply re-plans server-side
          ─▶ os.replace per file ─▶ op_log("rename", batch)

undo:     reverse the last batch (rename) or restore the recorded tags
```

The server never trusts a path from the client: `apply` recomputes the plan
from track ids and the template.

## Data model

| Table | Purpose |
| --- | --- |
| `jobs` | url, preset JSON, status, progress, speed, eta, output path, error, log tail |
| `tracks` | library index: relpath, tags, duration, bitrate, cover flag, search blob |
| `op_log` | undo journal: `rename` batches and `tags` edits with the previous values |
| `kv` | reserved for small settings |

SQLite runs in WAL mode with `synchronous=NORMAL`; a single connection behind an
`RLock` is enough for one user and keeps the code free of an ORM.

## SSE contract

`GET /api/events` streams `message` frames:

```json
{ "id": 42, "type": "job.updated", "data": { "id": "a1b2c3", "status": "running", "progress": 63.2, "speed": 1048576, "eta": 12 } }
```

The broker keeps the last 500 events, so `GET /api/events?since=41` replays the
gap after a reconnect. `EventSource` retries automatically.

## Packaging

| Artefact | Status | Notes |
| --- | --- | --- |
| Docker image | primary | bundles ffmpeg + deno, pinned yt-dlp |
| `pip install` | primary for dev | needs ffmpeg and a JS runtime on PATH |
| Nuitka `--onefile` | secondary | bundles yt-dlp, `imageio-ffmpeg`; still needs a JS runtime |

### Extractors go stale, so they are replaceable

yt-dlp is pinned by the release. YouTube changes break extractors within weeks,
so `app._ytdlp` prepends `$CONFIG_DIR/plugins` to `sys.path` **before** the
first `import yt_dlp`. `ytdlweb update-extractors` (or the Settings button)
downloads the newest pure-python wheel from PyPI into that directory; the next
restart picks it up. The UI shows `Extractor plugin: active (override)`.

This is the mitigation for the main weakness of a frozen build: it can be
patched without shipping a new binary.

### JavaScript runtime

Modern yt-dlp needs a JS runtime (deno by default) to solve YouTube player
challenges. `app/core/jsruntime.py` detects `deno`, `node` or `bun` on `PATH`
and passes `js_runtimes` to yt-dlp. The Docker image installs deno. Override
with `JS_RUNTIME=node=/usr/local/bin/node`.

## Known limits

- One user. No per-user libraries or quotas.
- The indexer is a synchronous walk capped at 20 000 files, triggered manually
  or on demand; there is no filesystem watcher.
- Search is `LIKE` over a denormalised blob, not FTS5.
- Library writes are whole-file rewrites (mutagen), not in-place patching.
