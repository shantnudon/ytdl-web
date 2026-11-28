# Security

ytdlweb downloads from the internet and edits files on your disk. Both need
boundaries. This document describes the model, not a guarantee.

## Defaults

| Setting | Default | Why |
| --- | --- | --- |
| `APP_HOST` | `127.0.0.1` | Not reachable from the network until you say so. |
| `APP_PASSWORD` | unset | Single-user localhost tool; set it before exposing a port. |
| `ALLOW_WRITE` | `false` | The library API is read-only until enabled. |
| Docker user | `PUID:PGID` (1000) | Never runs as root inside the container. |

## Threat model

The interesting attacker is someone who can send HTTP requests to the app.

| Threat | Control |
| --- | --- |
| Read/write files outside `LIBRARY_DIR` | Path jail (below) |
| Move files via a crafted rename template | Server re-plans from track IDs; template values are sanitised |
| Damage a file with a bad tag write | Temp-file copy + `os.replace` |
| Run arbitrary yt-dlp options | Presets are allow-listed in `app/core/options.py` |
| SSRF via the URL field | Only `http(s)` URLs; the value is handed to yt-dlp, never fetched by our own HTTP client |
| Stored XSS via tags/filenames | Svelte escapes by default; CSP forbids inline script |
| CSRF | `SameSite=Strict` cookie **and** a required `X-Requested-With: ytdlweb` header on mutations |
| Brute force on the password | In-process rate limit on `/api/auth/login` (8 per 5 min) |
| Frame/clickjacking | `X-Frame-Options: DENY` + `frame-ancestors` via CSP |
| Slow-client memory growth | SSE queues are bounded; frames are dropped, never buffered forever |

## Path jail

`app/library/safety.py` implements the only way to turn a client-supplied path
into a filesystem path:

```python
resolve_within(root, rel)
```

It rejects, in order:

1. `None`, empty or whitespace-only input
2. NUL bytes
3. absolute paths and Windows drive letters (`C:\...`)
4. any `..` segment
5. anything that, after `Path.resolve()`, is not inside the resolved root
   (this is what stops symlinks pointing outside the library)
6. (callers) any extension outside the audio allow-list

Every mutation re-derives the destination from the **database row**, not from
the request body. `POST /api/library/rename/apply` takes track IDs and a
template, then recomputes the plan; a client cannot request "move X to
../../etc/cron.d".

The test suite (`tests/test_safety.py`, `tests/test_rename.py`) covers traversal,
symlink escape, absolute paths, NUL bytes, collisions and template injection.

## Atomic writes

Tagging and cover art never modify the original in place:

```
source.mp3 ──copy──▶ .source.mp3.XXXX.tmp ──mutagen──▶ .tmp ──os.replace──▶ source.mp3
```

A crash or full disk can leave a `.tmp` file, never a truncated MP3.

## Deploying on a network

Checklist before you expose the port:

- [ ] `APP_PASSWORD` set to a long random value (`openssl rand -hex 32`)
- [ ] TLS terminated by a reverse proxy; app bound to `127.0.0.1` or a private
      container network
- [ ] `ALLOW_WRITE` only if you actually edit files through the UI
- [ ] `/music` mounted read-only (`:ro`) while you are only downloading
- [ ] `PUID`/`PGID` match the owner of the mounted directories
- [ ] Backups of the library and `$CONFIG/ytdlweb.db` (it stores the rename log)
- [ ] No public/multi-tenant instance — see [Legal](../README.md#legal)

## Known limitations

- One shared password, no per-user accounts, no audit trail of who did what.
- The password itself is stored in an HttpOnly session cookie; there is no expiry
  beyond 30 days and no server-side revocation (rotate `APP_PASSWORD`).
- The rate limiter is in-process and resets on restart; it is not a WAF.
- yt-dlp fetches the URL you give it. Treat the URL field as "the server will
  contact this host".
- Library indexing reads files as the process user. Do not point it at a
  directory with files you would not want summarised in the DB.

## Third-party binaries

| Component | Licence | Notes |
| --- | --- | --- |
| yt-dlp | Unlicense | permissive |
| ffmpeg (Docker: Debian package) | LGPL/GPL depending on build flags | Debian's build is the safer default |
| `imageio-ffmpeg` wheel (binary builds) | ships an FFmpeg build with its own terms | check before redistributing binaries |
| deno | MIT | single binary, installed from deno.land |

If you redistribute a binary that contains ffmpeg, you are redistributing
ffmpeg: keep the licence notices and make the corresponding source available if
the build is GPL.

## Reporting

Open a private security advisory on the repository (Security → Advisories)
rather than a public issue. Please include a minimal reproduction — the path
jail and rename engine are the parts most worth attacking.
