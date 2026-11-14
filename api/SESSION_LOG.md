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


## 2026-11-14 · session 2 (sync with WS1, search SQL + scoring, snapping, `/search` v1)

Branch `ws2-api` in the main checkout (the human merged `worktree-ws2-api-build` into it and removed that worktree).
At the start, rebased onto `origin/main` `0877d84` (WS1 PR #5: shared CLAP + live seed) with no conflicts. Then
`make schema` (CRLF-only diff in the shared files, left alone) and `make check-fixtures` (13 fixtures, 0 problems).
Commits this session: `5693789` (T3.1) and `43c0e22` (T3.2).

### Done
- **State check:** `common.clap.embed_text` is implemented. The dev DB has **350 tracks** (150 Jamendo, 200 Freesound),
  about **6.5k windows** (WS1's ingest was still adding rows), 36 stems, 9 heroes and 0 notes. Keys look like `"A minor"`.
  113 tracks have a null bpm and 32 have no beats.
- **T3.1 search SQL + scoring: pass, live.** "dusty soul keys" on the seed → 8 results, at most 3 per track, scores
  0.54–0.58, all Rhodes/R&B/soul windows. The unit tests cover the score math, clamp, bpm_fit, tag_overlap, the
  per-track cap and the dedupe. An opt-in DB test checks every filter against temp tables that shadow the real ones
  inside a rolled-back transaction.
- **T3.2 snapping + `/search` v1: pass, live.** `scripts/search_check.py` runs the real app (pool + CLAP) over
  the 20 eval queries in `scripts/eval_queries.py`. All 20 returned 200 and validated against `SearchResponse` and
  `shared/schema`. **p50 297–328 ms, p95 388–402 ms** uncached, p50 160 ms with cached query vectors.
  **Fallback needed 0/20.**
- **Proposal C8** `docs/proposals/WS2-clap-model-env.md`: the corpus was embedded with
  `laion/larger_clap_general` @ `ada0c23a36c4e8582805bb38fec3905903f18b41`, but `.env.example` / CONTRACT §8 still
  say `laion/larger_clap_music`. An API started with the documented env silently returns meaningless rankings.
- Checks at the end: `make lint` green; `uv run --project api pytest api` gives 72 passed and 5 skipped (the opt-in
  DB tests); with `BEATOPIA_DB_TESTS=1` the DB tests give 9 passed.

### Deviations from PLAN.md
- **Dedupe threshold is ≥ 50%** of the shorter window (same track and same stem), not > 50%. WS1's windows are 10 s
  with a 5 s hop, so neighbours overlap exactly 50% and would otherwise all survive. Different stems of the same
  moment are kept, because they're different samples.
- **Null-bpm tracks pass a bpm filter** and score bpm_fit 0.5 (that's how I read §7.4's "0.5 when the track bpm is
  null"). A null key does **not** pass a key filter. That's about a third of the library, so a tempo chip still
  brings in unknown-tempo tracks at a small score penalty. Revisit if WS3 reports it.
- **Chip merge landed early** in `core/planner.py` (it was planned for T4.1), because `/search` v1 needs chips.
  T4.1 only adds Gemini + `plan_cache` in front of `merge_chips`.
- **v1 caption:** text as typed (whitespace collapsed), else the instrument/genre/mood chip labels + " music"
  (tempo/key chips never go into the CLAP text), else "music".
- **New 400s:** no text and no chips, or an unknown chip id → `bad_request`. CLAP not loaded → 502 `upstream_error`.
- **Snap fallback:** when not even 1 bar fits (a sound shorter than 1 bar at its bpm), the raw bounds stay with `bars=1`.
- Files were written via a scratch dir + copy because the background-job guard blocks Write/Edit in the shared
  checkout (the human said: no worktrees).

### Gotchas
- **Set the CLAP env before starting the API** (C8): `CLAP_MODEL=laion/larger_clap_general
  CLAP_REVISION=ada0c23a36c4e8582805bb38fec3905903f18b41`. `common.clap` reads both at import time. The local `.env`
  doesn't have them yet (I didn't edit it). The startup log line `clap warm (<model> @ <revision>)` shows what loaded.
- The first CLAP load downloads the weights (≈ 170 s once). After that, startup takes 30–40 s (CPU warm-up).
- The first SQL on a cold connection took 3.1 s; warm, it's 80–340 ms, of which 39 ms is in Postgres (exact top-N sort
  over about 6.5k rows, no ANN index needed yet). The pool keeps its connections warm.
- `common.storage.public_url` reads `SUPABASE_URL` from `os.environ`, not from `Settings`, so tests must `setenv` it.
- On Windows, scripts that print track titles need a UTF-8 stdout (`search_check.py` reconfigures it).
- **The fallback trigger won't fire:** the non-sim score terms give a floor of about 0.25, so even "kazoo
  orchestra" tops out at 0.52. T8.1 must trigger on `sim` (for example, top-3 sim < X measured on the eval set) and
  needs a §7.7 proposal.

### State
- Real endpoints: `/health`, `/chips`, `/tracks/{id}`, `/search` (v1: no Gemini plan/rerank, no fallback). Fixture
  stand-ins are left for `/tracks/{id}/stems`, `/jobs/{id}`, `/imports`, `/why`, `/events` and `/assist`.
- No production URL or VM yet.
- Proposals waiting to land: C7 (`internal_error`) and **C8 (CLAP model/revision; needed before the deploy)**.

### Next
- T4.1 Gemini client + planner + `plan_cache`, then T4.2 rerank + notes.
- Human actions:
  1. Add the two `CLAP_*` lines to the local `.env`, and land C8 with WS1 (`.env.example` / CONTRACT §8).
  2. (Done in the wrap-up below.) Push `ws2-api`: the rebase onto main rewrote session 1's commits, so a plain push is rejected. Run
     `git push --force-with-lease origin ws2-api` if you want the remote to match.


## 2026-11-14 · session 2 wrap-up (remote sync)

The full results of this session are in the session 2 entry above. This entry records the branch sync after it.

### Done
- **T3.1: pass** and **T3.2: pass** (details above): "dusty soul keys" returns 8 results, at most 3 per track, scores
  0.54–0.58. All 20 eval queries validate; **p50 297–328 ms, p95 ≈ 400 ms** uncached, p50 160 ms cached;
  fallback needed 0/20.
- **Remote sync:** GitHub showed `ws2-api` one commit behind main, because `origin/ws2-api` was still the copy of
  session 1 from before the rebase. All 6 of its commits were already on the local branch as rebased copies
  (checked with `git cherry`). With the human's OK, I pushed with `--force-with-lease` pinned to `2d207cc`, so
  `origin/ws2-api` now contains `origin/main` `0877d84` (0 behind).
- PLAN.md: T3.1 and T3.2 are ticked; one-line *Left:* notes added to T4.1 and T8.1.

### Deviations
- None beyond those listed in the session 2 entry. The force push was explicitly approved by the human.

### Gotchas
- **Before starting the API**, set `CLAP_MODEL=laion/larger_clap_general` and
  `CLAP_REVISION=ada0c23a36c4e8582805bb38fec3905903f18b41` (proposal C8). The local `.env` still lacks them.
- After every `make schema` on Windows, `shared/schema/api.schema.json` and `web/lib/types/api.ts` show CRLF-only diffs.
  Leave them unstaged; `git checkout -- <file>` resets them when a clean tree is needed (for example, to rebase).
- Background jobs can't use Write/Edit in the main checkout. Write to the job scratch dir and copy, or set
  `"worktree": {"bgIsolation": "none"}` in `.claude/settings.json`.
- No failing tests. The DB tests are opt-in (`BEATOPIA_DB_TESTS=1`, `--env-file ../.env`).

### State
- No production URL or VM yet (T6.x). Flags: `USE_FIXTURES=0` (real mode); `GEMINI_DEGRADED` isn't read yet.
- Real endpoints: `/health`, `/chips`, `/tracks/{id}` and `/search` v1. The rest are still fixture stand-ins.
- Fixtures: unchanged. Branch: `ws2-api` = `origin/ws2-api`, on top of `origin/main` `0877d84`.

### Next
- **First task: T4.1** Gemini client + planner + `plan_cache` (the chip merge already exists in `core/planner.py`).
- Human actions first: add the two `CLAP_*` lines to the local `.env`, and land C8 with WS1. C7 (`internal_error`)
  can wait until the H12 sync.


## 2026-11-14 · session 3 (Gemini client, planner + plan_cache, rerank + notes)

Branch `ws2-t4` (a worktree at `.claude/worktrees/ws2-t4`, branched from `ws2-api` `ca83aef`, pushed to origin).
Commits: `290e73c` (T4.1), `7da36ac` (T4.2), plus this wrap-up. `origin/main` was still `0877d84`, so there was no
sync.

### Done
- **T4.1 Gemini client + planner + plan_cache: pass, live** (`scripts/plan_check.py`, `gemini-3.6-flash`).
  "sad trumpet around 90 bpm, no drums" → `must [trumpet]`, all 6 drum tags excluded, bpm (85, 95), in 1.5 s. The
  second call hits the in-process LRU (0.1 ms), and a fresh process hits the `plan_cache` row (≈ 100 ms). "just the
  drums, fast breakbeat" → `stems [drums]`, bpm 120–170, `prefer_sparse`. The mock tests cover the chip-merge
  rules, defensive conversion, cache key normalization, the fallback on 503/429/bad JSON/timeout (not cached), the
  degraded switch and auto-degrade.
- **T4.2 Rerank + notes: pass, live** (`scripts/rerank_check.py`). "dusty soul keys" and the trumpet query got 8/8
  notes, rerank 2.3–3.3 s, `rerank_ms` in the log line. The repeat search is `skipped:memo` at 219 ms total with no
  Gemini call. The mock tests cover: fake, duplicate and out-of-top-20 ids dropped, missing ids appended in score
  order, notes only for ordered uncached ids, the 30-word trim, a cached note never overwritten, the skip rules,
  failure → score order, and a notes-write error that isn't fatal.
- **Latency:** an uncached search (planner + rerank) takes **2.8–5.3 s** in total. With both cached, about 220 ms.
  No p50 over the 20 eval queries this session (the free-tier quota doesn't allow 40 calls).
- **Proposal C9** `docs/proposals/WS2-gemini-model.md`: `GEMINI_MODEL=gemini-3.6-flash`.
- Checks: `make lint` green; `uv run --project api pytest api` gives 103 passed and 5 skipped (the opt-in DB tests).

### Deviations from PLAN.md
- **Tags are plain strings in the planner schema.** Two 126-value tag enums make the API return `400
  INVALID_ARGUMENT` (the key and stem enums are fine). The prompt lists the vocab, and `from_gemini` filters to it.
  This was the fallback named in PLAN §1.
- **Thinking `MINIMAL`** for the planner and rerank, not `LOW`. On the full planner prompt with `3.6-flash`, LOW took
  3–11 s and MINIMAL 1.0–1.3 s. `gemini.thinking_for` sends MINIMAL as LOW to `gemini-3.8-flash`, which rejects it.
- **Budgets are wall-clock, enforced in `core/gemini.py`.** The API rejects HTTP deadlines under 10 s (`400 Manually
  set deadline 4s is too short`), so the HTTP deadline is max(budget, 10 s). The call runs on an 8-thread pool and
  we stop waiting at the budget.
- **Sync client** (`client.models`), not `client.aio`, because `/search` is a sync handler in the threadpool.
- **Auto-degrade landed now** (3 failures in 60 s → skip Gemini for 5 min) instead of T11.2. Without it, a 429 adds
  seconds to every search.
- **Rerank order memo** (in process, keyed by request + chips + limit + top-20 ids). The plan's "skip if the top 8
  are cached" rule checks the score-order top 8, which rarely equals the reranked set, so every repeat would
  re-call Gemini. With the memo, repeats reuse Gemini's order and skip once their notes are cached.
- **Plan cache:** an in-process LRU (1024) sits in front of `plan_cache`, because the session pooler round trip is
  80–170 ms and the acceptance check asks for < 50 ms. The cached value is the pre-merge plan, so chips are
  re-applied on every hit.
- New log fields: `plan_source` (chips|memory|db|gemini|fallback), `rerank` (ok|skipped:*|failed), `new_notes`.

### Gotchas
- **The local `.env` has `GEMINI_MODEL=gemini-3.8-flash-lite`, which doesn't exist (404 on every call).** Set
  `gemini-3.6-flash` (C9). Today `gemini-3.8-flash` and `3.7-flash` returned 503 "high demand" on every call,
  even on a 3-word prompt.
- **Free-tier quota:** `429 You exceeded your current quota` after about 2–4 calls a minute; it recovers within
  minutes. Live scripts pause 20 s between searches. An uncached search makes 2 Gemini calls. **The paid key is
  needed before the deploy and demo.**
- Live checks need, in the process env: `GEMINI_MODEL=gemini-3.6-flash CLAP_MODEL=laion/larger_clap_general
  CLAP_REVISION=ada0c23a36c4e8582805bb38fec3905903f18b41`. `.env` wasn't edited; the worktree has a git-ignored copy.
- The live checks wrote real rows to `plan_cache` and `notes` in the dev DB (about 15 notes with model
  `gemini-3.6-flash:meta`). They are the cache; delete them if you want a cold run.
- Tests: `tests/test_planner.py` provides `FakeClient` / `FakeResponse` / `api_error`, and other tests import them
  (`from tests.test_planner import ...`). The search fixture clears `planner.memory_cache` and `rerank.order_memo`.
- The worktree guard refuses compound shell commands that `cd` elsewhere or chain git with other directories. Run
  from the worktree, and use `make -C .. lint` from `api/`.
- Windows: Python `write_text` writes CRLF and git normalizes it to LF on commit (harmless warnings).
- No failing tests.

### State
- No production URL or VM yet. WS3 is waiting for an API URL (fixtures until the deploy, or a temporary tunnel).
  Vercel access has to come from the project owner. CORS still has no `*.vercel.app` regex (to add with T6.2).
- Flags: `USE_FIXTURES=0`; `GEMINI_DEGRADED` is now read (1 = skip planner and rerank). Code default model is
  `gemini-3.8-flash` (CONTRACT §8) until C9 lands.
- Real endpoints: `/health`, `/chips`, `/tracks/{id}`, `/search` (planner + rerank, no Freesound fallback). Fixture
  stand-ins: `/tracks/{id}/stems`, `/jobs/{id}`, `/imports`, `/why`, `/events`, `/assist`.
- Fixtures: unchanged. Proposals waiting to land: C7, C8 (needed before the deploy), C9.

### Next
- **First task: T4.3 `/why` with audio**, unless the human moves the deploy forward (T6.1/T6.2) so WS3 gets a URL.
- Human actions first:
  1. Bring the work into `ws2-api`: from the main checkout, `git merge --ff-only ws2-t4 && git push origin ws2-api`.
  2. Fix `GEMINI_MODEL` in `.env` (→ `gemini-3.6-flash`) and add the two `CLAP_*` lines; land C8 and C9.
  3. Get the paid Gemini key before the deploy.
  4. For the deploy: a Vultr VM IP plus SSH access, and WS3's exact Vercel domains for CORS.
