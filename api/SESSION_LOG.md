# WS2 session log

## 2026-11-14 · session 1 (plan sync, core wiring, chips, tracks)

Branch `worktree-ws2-api-build` (pushed), based on local `ws2-api` after the rebase onto `cb05f68`. Last commit
before this entry: `dafd768`.

### Done
- **Plan sync.** PLAN.md matches the final contract. C1–C5 landed unchanged in `cb05f68` and are no longer
  assumptions. The proposal is marked landed. Conditional follow-ups C4b, C5b and C6 remain, plus the new C7.
- **T1.1 Settings, errors, fixture mode: pass.** All 13 `test_stubs.py` tests pass unchanged. An unknown route gives
  404 `not_found`, a wrong method gives 405 `bad_request`, and an unhandled error gives 500 `internal_error`.
- **T1.2 DB pool, lifespan, timing: pass.** Checked against the dev Supabase: the pool opens, pgvector is 0.8.2, all
  7 contract tables exist, `/health` returns 200 in 8–14 ms with one JSON log line, and the pool closes on shutdown.
  An unreachable DB fails startup with a clear message (tested).
- **T2.1 `/chips`: pass.** The generated response equals `shared/fixtures/chips.json` exactly (154 chips: 60
  instrument, 30 genre, 30 mood, 10 tempo, 24 key).
- **T2.2 `/tracks/{id}`: pass, with a caveat.** The DB had 0 tracks (no WS1 seed yet). The real SQL was checked by
  `test_fetch_track_detail_against_db` on the dev DB inside a rolled-back transaction; the DB was empty afterwards.
  The 404 shape is tested.
- Checks at the end: `make lint` green (ruff check, ruff format, eslint, tsc); `uv run --project api pytest api`
  gives 36 passed and 1 skipped (the opt-in DB test). `scripts/check_fixtures.py`: 13 fixtures, 0 problems.
- No `/search` latency numbers yet, because search isn't built.

### Deviations from PLAN.md
- **Real mode serves fixture stand-ins for unbuilt endpoints**, with a startup warning that lists them. That way
  `make dev-api` keeps answering every endpoint while I build. The list must be empty before the deploy (T6.2).
  Currently left: `/search`, `/tracks/{id}/stems`, `/jobs/{id}`, `/imports`, `/why`, `/events`, `/assist`.
- **New error code `internal_error` (500)** for unhandled exceptions. Not in the contract yet: proposal C7,
  `docs/proposals/WS2-internal-error-code.md`.
- **Chip slugs follow the fixture** (`r&b` → `genre.rnb`), not the `r_b` the plan said.
- **CLAP warm-up doesn't fail startup** while `common.clap.embed_text` raises `NotImplementedError`; it only logs a
  warning, and `app.state.clap_ready` is False.
- **Real mode also requires `SUPABASE_URL`** (for audio URLs) and loads the vocab at startup.
- **The DB connection is probed** once directly before the pool opens, so a bad URL or a missing pgvector shows the
  real error instead of a `PoolTimeout`.
- Work is on `worktree-ws2-api-build`, not `ws2-api` (see Gotchas).

### Gotchas
- **`ws2-api` vs `origin/ws2-api` have diverged** because of the rebase. Updating the remote needs a force-push,
  which the agent doesn't do. The human runs this from the main checkout: `git merge --ff-only worktree-ws2-api-build && git push --force-with-lease origin ws2-api`.
- The main checkout has uncommitted diffs to `shared/schema/api.schema.json` and `web/lib/types/api.ts`. They are
  **CRLF-only** (from `make schema` on Windows), are shared paths, and were left alone.
- The shell exports `VIRTUAL_ENV` pointing at the main checkout's `api/.venv`, so `uv` prints a "does not match"
  warning in the worktree. That's harmless: uv uses the worktree's own `api/.venv`, which now exists, and so does
  `web/node_modules`.
- If you run a script from outside `api/` with the main checkout's venv, Python imports the **main checkout's**
  `app` (editable install). Set `PYTHONPATH=<worktree>/api`.
- Tests default to fixture mode (`tests/conftest.py` sets `USE_FIXTURES=1`). Real-mode tests build their own app
  with `create_app(Settings.from_env({...}))`.
- Opt-in DB test: `BEATOPIA_DB_TESTS=1 DATABASE_URL=... uv run --project api pytest api/tests/test_tracks.py`.
- WS1 stubs still raise `NotImplementedError`: `common.clap.embed_text/embed_audio`, `common.storage.upload`,
  `common.audio.*`, `common.analysis.*`, `common.db.connect` (the API doesn't use that one; it has its own pool).
  `common.storage.public_url` works.
- On Windows, `asyncio.sleep` inside a timed stage can measure far less than requested, so timing tests use
  `time.sleep`. libpq's minimum `connect_timeout` is 2 s.
- Versions: google-genai 3.3.0, psycopg 3.3.9, psycopg-pool 3.3.3, pgvector extension 0.8.2, default model
  `gemini-3.8-flash`.

### State
- No production URL or VM yet; the deploy is T6.x at H10–H12.
- Flags: server default `USE_FIXTURES=0` (real mode, with stand-ins for unbuilt endpoints). `GEMINI_DEGRADED` isn't
  read by any code yet.
- Dev DB: schema present, **0 rows** in every table.
- Fixtures: unchanged.

### Next
- **First task: T3.1 search SQL + scoring.** Unit tests can be written now. The live check needs WS1's seed and a
  real `common.clap.embed_text`.
- Human actions:
  1. Move `ws2-api` to this branch with the force-with-lease command above.
  2. Land C7 (`internal_error`) at the H12 sync.
  3. Ask WS1 for the seed ETA (needed for the H3 gate and the T2.2 re-check).
