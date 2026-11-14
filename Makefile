# Shared Makefile (contract path). Works with GNU make (macOS/Linux) and mingw32-make + Git Bash (Windows).
# Python steps need uv; web steps need Node + pnpm. The *-py / *-web targets split them for one-toolchain laptops.

ENV_FILE := $(if $(wildcard .env),--env-file .env,)
PY_PROJECTS := common ingest worker api

.PHONY: help install schema check-fixtures fixture-audio db-init dev-api dev-worker dev-web \
        test test-py test-web lint lint-py lint-web format

help:
	@echo "install schema check-fixtures fixture-audio db-init dev-api dev-worker dev-web test lint format"

install:  ## uv sync every Python project + pnpm install
	for p in $(PY_PROJECTS); do (cd $$p && uv sync) || exit 1; done
	cd web && pnpm install

schema:  ## Pydantic -> shared/schema/api.schema.json -> web/lib/types/api.ts
	uv run --project api python scripts/export_schema.py

check-fixtures:  ## validate shared/fixtures against the schema
	uv run --project api python scripts/check_fixtures.py

fixture-audio:  ## regenerate web/public/fixtures/audio/*.wav
	uv run --project common python scripts/make_fixture_audio.py

db-init:  ## apply db/migrations and create the "audio" bucket (needs .env)
	uv run --project common python scripts/db_init.py

dev-api:  ## uvicorn on :8000
	uv run --project api $(ENV_FILE) uvicorn app.main:app --reload --reload-dir api --port 8000

dev-worker:  ## job worker
	uv run --project worker $(ENV_FILE) python -m worker.main

dev-web:  ## next dev on :3000
	cd web && pnpm dev

test: test-py test-web  ## pytest + vitest

test-py:
	for p in $(PY_PROJECTS); do uv run --project $$p pytest -q $$p || exit 1; done

test-web:
	cd web && pnpm test

lint: lint-py lint-web  ## ruff + eslint + tsc --noEmit

lint-py:
	uv run --project api ruff check $(PY_PROJECTS) scripts
	uv run --project api ruff format --check $(PY_PROJECTS) scripts

lint-web:
	cd web && pnpm lint && pnpm typecheck

format:
	uv run --project api ruff check --fix $(PY_PROJECTS) scripts
	uv run --project api ruff format $(PY_PROJECTS) scripts
