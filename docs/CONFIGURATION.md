# Configuration

Every setting is an environment variable, optionally placed in `.env` in the
working directory. All are optional; the defaults give a localhost-only,
read-only instance under `~/.local/share/ytdlweb`.

## Reference

| Variable | Default | Description |
| --- | --- | --- |
| `APP_TOKEN` | _empty_ | When set, all `/api` routes except auth/health require it. Accepts `Authorization: Bearer <token>` or the cookie set by the login screen. |
| `APP_HOST` | `127.0.0.1` | Bind address. `0.0.0.0` in Docker (the container is the boundary). |
| `APP_PORT` | `8080` | HTTP port. |
| `LOG_LEVEL` | `info` | uvicorn log level. |
| `YTDLWEB_DATA_DIR` | `~/.local/share/ytdlweb` | Base for `DOWNLOAD_DIR`, `LIBRARY_DIR`, `CONFIG_DIR`. |
| `DOWNLOAD_DIR` | `$DATA/downloads` | Where downloads are written. |
| `LIBRARY_DIR` | `$DATA/library` | Root of the music library. **All** library paths are jailed to this directory. |
| `CONFIG_DIR` | `$DATA/config` | SQLite DB, `cookies.txt`, `archive.txt`, extractor plugins. |
| `STATIC_DIR` | `app/static` | Built SPA. Only change this for custom builds. |
| `ALLOW_WRITE` | `false` | Master switch for tag edits, cover art and renames. |
| `MAX_CONCURRENT` | `3` | Parallel download workers (each runs one yt-dlp instance). |
| `FFMPEG_PATH` | _auto_ | Explicit ffmpeg binary. |
| `COOKIES_FILE` | `$CONFIG/cookies.txt` | Netscape cookies file. |
| `JS_RUNTIME` | _auto_ | `deno`, `node`, `bun`, or `node=/path/to/node`. |
| `PUID` / `PGID` | `1000` | Docker only: uid/gid for mounted volumes. |
| `UMASK` | `002` | Docker only: permissions for newly created files. |
| `CHOWN_ON_START` | `true` | Docker only: chown `/config` and `/downloads` at boot (`/music` is never touched). |

## ffmpeg resolution order

1. `FFMPEG_PATH`, if it points at a file.
2. `imageio_ffmpeg.get_ffmpeg_exe()` (present in binary builds).
3. `ffmpeg` on `PATH`.

`/api/system` reports the resolved path and `ffmpeg_ok`.

## JavaScript runtime

yt-dlp needs a JS runtime for YouTube's player challenges. Detection order is
the `JS_RUNTIME` override, then `deno`, `node`, `bun` on `PATH`. The Docker
image ships deno; a source install needs one of them for YouTube to work
reliably.

```bash
JS_RUNTIME=node                       # use node from PATH
JS_RUNTIME=deno=/usr/local/bin/deno   # explicit binary
```

`GET /api/system` exposes `js_runtime.runtimes` and `paths`.

## Examples

### Local, read-only

```bash
ytdlweb serve
# http://127.0.0.1:8080, library at ~/.local/share/ytdlweb/library
```

### Local with library editing

```bash
LIBRARY_DIR="$HOME/Music" \
ALLOW_WRITE=true \
ytdlweb serve
```

### Docker behind a reverse proxy

```yaml
services:
  ytdlweb:
    image: ghcr.io/your-user/ytdl-web:latest
    environment:
      APP_TOKEN: "${APP_TOKEN:?set a long random token}"
      ALLOW_WRITE: "true"
      PUID: "1000"
      PGID: "1000"
    volumes:
      - ./config:/config
      - ./downloads:/downloads
      - /srv/media/Music:/music
    ports:
      - "127.0.0.1:8080:8080"   # only the proxy can reach it
```

Then terminate TLS in Caddy/nginx and forward to `127.0.0.1:8080`.

### systemd unit

```ini
[Unit]
Description=ytdlweb
After=network-online.target

[Service]
User=media
WorkingDirectory=/home/media/ytdl-web
Environment=APP_TOKEN=change-me
Environment=ALLOW_WRITE=true
Environment=LIBRARY_DIR=/srv/media/Music
ExecStart=/home/media/ytdl-web/.venv/bin/ytdlweb serve
Restart=on-failure
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

## Presets

The UI sends a preset object; `app/core/options.py` validates it against
`DEFAULT_PRESET` and drops unknown keys.

| Key | Values | Notes |
| --- | --- | --- |
| `mode` | `video`, `audio` | audio uses `bestaudio` + `FFmpegExtractAudio` |
| `quality` | `best`, `2160`, `1440`, `1080`, `720`, `480`, `360` | resolution cap for video |
| `audio_format` | `mp3`, `m4a`, `opus`, `flac`, `aac`, `wav` | |
| `audio_quality` | `0` (VBR best), `320`, `256`, `192`, `128` | |
| `outtmpl` | yt-dlp template | `%(ext)s` is appended if missing; `..` is rejected |
| `playlist_items` | `1-5,8` | empty means all |
| `subtitles` / `embed_subs` | bool | also downloads auto-generated subs |
| `embed_metadata`, `embed_thumbnail` | bool | |
| `sponsorblock` | `off`, `mark`, `remove` | `remove` re-encodes through ffmpeg |
| `archive` | bool | skips anything already in `$CONFIG/archive.txt` |
| `force` | bool | ignore the archive and overwrite, so the same URL can be re-fetched in another format |
| `rate_limit` | `500K`, `5M` | bytes per second |
| `concurrent_fragments` | 1–16 | |

## Cookies

Upload a Netscape `cookies.txt` from Settings. It is written to
`$CONFIG/cookies.txt` with mode `0600`. Browser cookie import
(`--cookies-from-browser`) is intentionally not supported: it cannot work inside
a container and silently reads the host's secrets.

Export cookies with a browser extension or:

```bash
yt-dlp --cookies-from-browser firefox --cookies cookies.txt --skip-download URL
```
