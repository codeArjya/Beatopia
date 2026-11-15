# syntax=docker/dockerfile:1
# Beatopia job worker (code by WS1, image by WS2). Build from the repo root:
#   docker build -f deploy/worker.Dockerfile -t beatopia-worker .
# CPU torch (from the lock). Demucs weights land in /root/.cache/torch (named volume in compose).
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/root/.cache/huggingface \
    TORCH_HOME=/root/.cache/torch

WORKDIR /app

COPY worker/pyproject.toml worker/uv.lock worker/README.md worker/
COPY common/pyproject.toml common/README.md common/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd worker && uv sync --frozen --no-dev --no-install-project --no-install-package common

COPY common/ common/
COPY worker/ worker/
COPY ingest/vocab.txt ingest/vocab.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    cd worker && uv sync --frozen --no-dev

ENV PATH="/app/worker/.venv/bin:$PATH"
CMD ["python", "-m", "worker.main"]
