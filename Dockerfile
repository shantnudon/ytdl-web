# syntax=docker/dockerfile:1

# ---- UI build ---------------------------------------------------------------
FROM node:26-alpine AS ui
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-fund --no-audit || npm install --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# ---- Runtime ----------------------------------------------------------------
FROM python:3.15-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    YTDLWEB_DATA_DIR=/config \
    DOWNLOAD_DIR=/downloads \
    LIBRARY_DIR=/music \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080

# ffmpeg: merging/transcoding. deno: yt-dlp needs a JS runtime for YouTube.
# gosu: drop privileges to PUID/PGID so mounted files keep the host owner.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg gosu curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- -y \
    && deno --version

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY --from=ui /src/app/static ./app/static
RUN pip install --no-cache-dir .

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

VOLUME ["/config", "/downloads", "/music"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["ytdlweb", "serve"]
