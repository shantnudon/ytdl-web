# Contributing

Thanks for taking a look. This is a small, opinionated tool: single user,
self-hosted, no multi-tenant features.

## Setup

```bash
make install      # venv + npm dependencies
make build-ui     # build the SPA into app/static
make test
make dev          # uvicorn with reload on :8080
```

For frontend work run `make ui` (Vite on :5173, proxying `/api` to :8080) next
to `make dev`.

## Ground rules

- **Paths from the client are hostile.** Any new filesystem operation must go
  through `app/library/safety.py::resolve_within` and, for writes, through
  `atomic_write`.
- **yt-dlp is only imported by `app/_ytdlp.py`.** Ruff enforces this via a
  banned-api rule; the extractor plugin path must be on `sys.path` first.
- **Presets are allow-listed.** Never pass a request body straight into
  yt-dlp options.
- **Blocks the loop, blocks the app.** yt-dlp and mutagen calls that touch the
  network or large files run in `asyncio.to_thread`.
- **New mutation endpoint?** Add `dependencies=[WriteGuard]`, log an undo entry
  in `op_log`, and write a test that tries to escape the library root.

## Tests

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
```

ffmpeg is required for the tag tests; they skip when it is missing. Network
tests are not part of the suite on purpose.

## Pull requests

- One topic per PR, with a short "why" in the description.
- Keep the diff focused; avoid drive-by reformatting.
- If you change the API, update `docs/CONFIGURATION.md` or `docs/ARCHITECTURE.md`.
- Screenshots for UI changes are welcome.

## Commit messages

Plain imperative subject (`fix: reject symlinked library roots`), body optional.
