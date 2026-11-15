# Roadmap

## Shipped in 0.1

- Download queue with SSE progress, cancel/retry, restart-safe `.part` resume
- Video and audio presets, metadata/thumbnail/subtitle embedding, SponsorBlock
- Playlist probe with a preview list and `playlist_items` selection
- `cookies.txt` upload, download archive, rate limiting
- Library index, tag editing, cover art, template renames with preview/apply/undo
- Token auth, CSRF guard, path jail, atomic tag writes
- Docker image with ffmpeg + deno, Nuitka onefile build script

## Next

- **FTS5 search** — swap the `LIKE` scan for a contentless FTS5 table once
  libraries get large.
- **Filesystem watcher** — incremental rescans via inotify/FSEvents instead of a
  full walk.
- **Trim / normalize** — the user asked for tag editing only in v1; ffmpeg is
  already there, so `loudnorm` and lossless cut are the natural next step.
- **Duplicate detection** — `fpcalc` (chromaprint) fingerprints in the indexer.
- **Subtitle/format picker** — expose the probed format list instead of presets
  only.
- **Multi-arch images** — build `linux/arm64` alongside `amd64` in CI.
- **i18n** — UI strings in Hindi and English.

## Explicitly out of scope

- Public multi-user hosting, accounts, quotas
- Hosted demo instance
- Re-uploading or redistributing downloaded media
- Browser cookie extraction inside the container
