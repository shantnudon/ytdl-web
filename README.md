# ytdlweb

Self-hosted **yt-dlp web UI** with a local **music library manager**.

Download videos, playlists and audio from thousands of sites, manage your queue
from a browser, then fix up the resulting MP3/M4A/FLAC files — tags, cover art
and filename templates — from the same interface.

Built for a single user on a homelab box or a local machine. Ships as a Docker
image, a Python package, or a single-file binary.

> **Scope:** this is a personal, self-hosted tool. It intentionally has no
> multi-user accounts and no hosted public instance. See [Legal](#legal).

---

## Features

**Downloader**

- Any site yt-dlp supports (YouTube, Vimeo, SoundCloud, Bandcamp, ...)
- Video presets with a resolution cap, or audio-only to `mp3` / `m4a` / `opus` / `flac`
- Playlists: probe first, pick a range (`1-5,8`), then download
- Live progress over SSE: percent, speed, ETA, cancel/retry per job
- Crash-safe queue: jobs survive a restart and resume from `.part` files
- Metadata is fetched as you paste a URL, so jobs show real titles immediately
- Re-download a URL in a different format (the archive is bypassed after a confirm)
- Download defaults (preset, rename template) are stored server-side
- Embed metadata, cover art, subtitles, chapters; SponsorBlock mark/remove
- `cookies.txt` upload for age-restricted or member-only content
- Download archive: re-running a URL never re-downloads the same video
- Rate limiting and concurrent fragment downloads
- Auto-detects a JavaScript runtime (deno/node/bun) — required by modern yt-dlp for YouTube

**Library**

- Index a mounted music directory into SQLite, search it from the UI
- Edit ID3 / MP4 / Vorbis tags, upload cover art
- Filename templates (`{artist}/{album}/{track:02d} - {title}`) with a
  mandatory preview step before anything is moved
- Undo for the last rename batch and the last tag edit
- Atomic writes: a crash mid-edit cannot truncate your audio file
- Read-only by default — writes require `ALLOW_WRITE=true`

---

## Quick start

### Docker (recommended)

```bash
docker run -d \
  --name ytdlweb \
  -p 8080:8080 \
  -e APP_TOKEN=change-me \
  -e ALLOW_WRITE=true \
  -e PUID=1000 -e PGID=1000 \
  -v "$PWD/downloads:/downloads" \
  -v "$HOME/Music:/music" \
  -v "$PWD/config:/config" \
  ghcr.io/your-user/ytdl-web:latest
```

Or with compose:

```bash
cp .env.example .env
docker compose up -d
```

Open <http://localhost:8080>.

### Building and publishing on GitHub

The repo is set up so that pushing is all you do — GitHub Actions builds the
image and publishes it to GHCR (no registry account, no local Docker, no
secrets):

```bash
git remote add origin git@github.com:<you>/ytdl-web.git
git push -u origin main
```

| Workflow | Trigger | Does |
| --- | --- | --- |
| `ci.yml` | push / PR | ruff, pytest on 3.11–3.13, SPA build |
| `docker.yml` | push to `main`, tags, PR | multi-arch image → `ghcr.io/<you>/ytdl-web`; PRs build + smoke-test only |
| `binaries.yml` | `v*` tags, manual | Nuitka onefile archives attached to the Release |

First push yields `:edge`, `:latest` and `:sha-<commit>`. Make the package public
once (Packages → Package settings → Change visibility → Public), or add a
`GHCR_PAT` secret so the workflow does it. Release with:

```bash
git tag -a v0.1.0 -m "ytdlweb 0.1.0" && git push origin v0.1.0
```

Full details, tags, and troubleshooting: [docs/PUBLISHING.md](docs/PUBLISHING.md).

### From source

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

cd frontend && npm install && npm run build && cd ..
.venv/bin/ytdlweb serve
```

### Single-file binary

Grab the archive for your platform from the GitHub releases page, extract it and
run `./ytdlweb`. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#packaging) for
what is bundled and how extractor updates work.

---

## Configuration

Every setting is an environment variable (or a `.env` entry). Nothing is
required.

| Variable | Default | Description |
| --- | --- | --- |
| `APP_TOKEN` | _empty_ | Enables auth. All `/api` routes then need this token. |
| `APP_HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` inside Docker. |
| `APP_PORT` | `8080` | HTTP port. |
| `YTDLWEB_DATA_DIR` | `~/.local/share/ytdlweb` | Base directory for state. |
| `DOWNLOAD_DIR` | `$DATA_DIR/downloads` | Where downloads land. |
| `LIBRARY_DIR` | `$DATA_DIR/library` | Root of the music library (the write jail). |
| `CONFIG_DIR` | `$DATA_DIR/config` | SQLite DB, cookies, extractor plugins. |
| `ALLOW_WRITE` | `false` | Enables tag edits, cover art and renames. |
| `MAX_CONCURRENT` | `3` | Parallel download workers. |
| `FFMPEG_PATH` | _auto_ | Explicit ffmpeg; otherwise bundled/PATH lookup. |
| `JS_RUNTIME` | _auto_ | `deno`, `node`, `bun`, or `node=/path/to/node`. |
| `COOKIES_FILE` | `$CONFIG_DIR/cookies.txt` | Netscape cookies file. |
| `PUID` / `PGID` | `1000` | Docker only: file ownership of mounted volumes. |
| `UMASK` | `002` | Docker only: permissions for new files. |

Full reference: [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

---

## Music library safety model

The library editor is the riskiest part of this project, so the rules are
explicit:

1. Every path is resolved with `Path.resolve()` and must stay under
   `LIBRARY_DIR`. Absolute paths, `..`, null bytes and symlinks that escape the
   root are rejected with `400`.
2. API responses never expose filesystem paths; tracks are addressed by opaque
   IDs.
3. Tag writes go to a sibling temp file which is then `os.replace()`d, so an
   interrupted save leaves the original intact.
4. Renames are two-phase: `preview` returns a plan, `apply` executes it. Files
   whose size/mtime changed in between are skipped.
5. The last rename batch and the last tag edit can be undone from the UI.
6. Mutations are off unless `ALLOW_WRITE=true`.

Read [docs/SECURITY.md](docs/SECURITY.md) before exposing the app to a network.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | request flow, concurrency model, job state machine, packaging |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | every env var, presets, ffmpeg/JS runtime resolution |
| [docs/SECURITY.md](docs/SECURITY.md) | threat model, path jail, deployment checklist, licences |
| [docs/ROADMAP.md](docs/ROADMAP.md) | what shipped, what is next, what is out of scope |
| [docs/PUBLISHING.md](docs/PUBLISHING.md) | GitHub Actions → GHCR, tags, making the package public |
| [CONTRIBUTING.md](CONTRIBUTING.md) | dev setup and the ground rules |

---

## Development

```bash
make install     # venv + npm deps
make dev         # build the UI, then run uvicorn with reload
make ui          # vite dev server with /api proxy (run alongside make dev)
make test        # pytest
make lint        # ruff
```

Layout:

```
app/            FastAPI backend, SQLite store, yt-dlp wrapper
app/library/    safety jail, tagging, indexer, rename engine
frontend/       Svelte 5 + Vite SPA (builds into app/static)
docs/           architecture, configuration, security, roadmap
tests/          unit + API tests
```

---

## Legal

yt-dlp downloads content from third-party services; doing so may violate their
terms of service and local copyright law. This project is intended for content
you own, content licensed for reuse, and personal archiving where permitted.

Do not deploy a public instance that lets strangers download content. The
maintainers provide the software only and take no responsibility for how it is
used. Bundled ffmpeg builds may carry their own licence terms — see
[docs/SECURITY.md](docs/SECURITY.md#third-party-binaries).

## License

MIT — see [LICENSE](LICENSE).
