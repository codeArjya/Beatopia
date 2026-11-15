# syntax=docker/dockerfile:1
# Beatopia API (WS2). Build from the repo root:  docker build -f deploy/api.Dockerfile -t beatopia-api .
# Layout inside the image mirrors the repo (/app/api, /app/common, /app/ingest/vocab.txt, /app/shared) because
# app.core.settings resolves REPO_ROOT from its own file path.
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /usr/local/bin/

# ffmpeg: /why cuts audio excerpts over HTTP (core/excerpt.py); librosa/soundfile need libsndfile.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/root/.cache/huggingface

WORKDIR /app

# 1) dependencies only (cached unless a lockfile changes). torch comes from the CPU index per the lock.
COPY api/pyproject.toml api/uv.lock api/README.md api/
COPY common/pyproject.toml common/README.md common/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd api && uv sync --frozen --no-dev --no-install-project --no-install-package common

# 2) sources
COPY common/ common/
COPY api/ api/
COPY ingest/vocab.txt ingest/vocab.txt
COPY shared/ shared/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd api && uv sync --frozen --no-dev

WORKDIR /app/api
ENV PATH="/app/api/.venv/bin:$PATH"
# Revision stamp (deploy.sh passes the git sha): readable via the OCI label, and the API returns it in
# X-Beatopia-Revision. Kept last so changing it never invalidates the dependency layers.
ARG REVISION=unknown
LABEL org.opencontainers.image.revision=$REVISION org.opencontainers.image.title=beatopia-api
ENV BEATOPIA_REVISION=$REVISION
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=240s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1
# One worker process: CLAP is a ~1 GB singleton; sync handlers run in uvicorn's threadpool.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
