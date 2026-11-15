# Publishing from GitHub

Everything builds on GitHub's runners. No local Docker, no registry account, no
secrets are required for the default path: the image goes to the GitHub
Container Registry (GHCR) using the workflow's own `GITHUB_TOKEN`.

## What runs where

| Workflow | Trigger | Result |
| --- | --- | --- |
| `.github/workflows/ci.yml` | push to `main`, PRs, manual | ruff + pytest on Python 3.11/3.12/3.13, SPA build check |
| `.github/workflows/docker.yml` | push to `main`, `v*` tags, PRs, manual | multi-arch image pushed to `ghcr.io/<owner>/<repo>`; PRs build amd64 only and smoke-test it |
| `.github/workflows/binaries.yml` | `v*` tags, manual | Nuitka onefile archives + `SHA256SUMS.txt` attached to the Release |

The Docker workflow is independent of the binaries workflow, so a failing
Windows build never blocks the image.

## One-time setup

1. Create the repository (public is fine — Actions minutes are free for public
   repos) and push:

   ```bash
   git remote add origin git@github.com:<you>/ytdl-web.git
   git push -u origin main
   ```

2. Nothing else. `permissions: packages: write` in `docker.yml` is enough; the
   repository's default workflow permission setting does not need to change
   because the workflow declares what it needs.

3. The first run publishes:

   ```
   ghcr.io/<you>/ytdl-web:edge
   ghcr.io/<you>/ytdl-web:latest
   ghcr.io/<you>/ytdl-web:sha-<commit>
   ```

## Make the package public

GHCR packages are **private by default**, even when the repository is public.
Anonymous `docker pull` fails until you flip this once.

**Manual (always works):** repository → *Packages* → `ytdl-web` → *Package
settings* → *Danger Zone* → *Change visibility* → Public.

**Automated:** create a personal access token with `write:packages`, add it as
the repository secret `GHCR_PAT`. The workflow then runs:

```bash
gh api --method PATCH /user/packages/container/ytdl-web/visibility \
  -f visibility=public
```

That step is `continue-on-error: true`, so its absence only prints a notice.
For an organisation-owned package the token must have admin on the package and
the workflow falls back to the `/orgs/<owner>/...` endpoint.

## Cutting a release

```bash
# keep the version in sync: pyproject.toml AND app/__init__.py
git tag -a v0.1.0 -m "ytdlweb 0.1.0"
git push origin v0.1.0
```

This produces:

| Tag | Meaning |
| --- | --- |
| `:0.1.0` | exact release |
| `:0.1` | minor line, moves with patch releases |
| `:latest` | newest release or `main` build |
| `:edge` | every push to `main` |
| `:sha-abc1234` | immutable, per commit |

and, from `binaries.yml`, a GitHub Release with
`ytdlweb-linux-x86_64`, `ytdlweb-macos-arm64`, `ytdlweb-windows-x86_64.exe`
and checksums.

`/api/health` and `/api/system` report the version, so bumping
`app/__init__.py` is what makes `:0.1.0` self-identifying.

## Running the published image

```bash
docker run -d --name ytdlweb -p 8080:8080 \
  -e APP_TOKEN="$(openssl rand -hex 32)" \
  -e ALLOW_WRITE=true \
  -e PUID="$(id -u)" -e PGID="$(id -g)" \
  -v "$PWD/config:/config" \
  -v "$PWD/downloads:/downloads" \
  -v "$HOME/Music:/music" \
  ghcr.io/<you>/ytdl-web:latest
```

Pin `:0.1.0` in production and bump deliberately; `:latest` moves.

## Build details

- **Platforms:** `linux/amd64,linux/arm64`. arm64 runs under QEMU on x86
  runners, so it takes a few minutes longer — PR builds are amd64-only to keep
  feedback fast.
- **Cache:** `type=gha` for layers and buildx. First run is the slow one;
  afterwards only the `app/` layer rebuilds.
- **PR builds** use `load: true` (no registry push) and then start the container
  and curl `/api/health` and `/api/system`. A broken entrypoint fails the PR.
- **Reproducibility:** the image installs yt-dlp from `pyproject.toml`; the
  build date is therefore meaningful. Refresh extractors at runtime with
  `ytdlweb update-extractors` if a site breaks before the next release.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `denied: permission_denied` on push | The job lost `packages: write`, or a fork ran the workflow. Forks never push. |
| `manifest unknown` when pulling | Package is private or the tag does not exist yet. Log in or make it public. |
| `npm ci` fails on the runner | `frontend/package-lock.json` is out of sync. Run `npm install` locally and commit the lockfile. |
| Smoke test fails on a PR | The container did not start. Reproduce with `docker compose up --build`, then `docker logs`. |
| arm64 build times out | QEMU emulation is slow. Re-run, or set `PLATFORMS: linux/amd64` temporarily. |
| Deno install fails | `deno.land` hiccup during the image build. Re-run the job. |
| Binaries fail, image is fine | Expected: separate workflow. Fix or ignore without blocking the image. |

## Optional: mirror to Docker Hub

Add a second login and a second `images:` line:

```yaml
      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
```

```yaml
        with:
          images: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
            docker.io/<you>/ytdl-web
```

## Repository checklist

- [ ] Actions enabled (default for a new repo)
- [ ] Package visibility set to public (above)
- [ ] `main` protected, PRs require the `CI` check
- [ ] Dependabot enabled — `.github/dependabot.yml` covers pip, npm, Docker and Actions
- [ ] Private vulnerability reporting enabled (see [SECURITY.md](SECURITY.md))
