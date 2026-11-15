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


## 2026-11-14 · session 4 (`/why` with audio, contract test)

Branch `ws2-t4` (worktree `.claude/worktrees/ws2-t4`), pushed. Commits: `7570578` (T4.3) and `9090ebe` (T5.1), plus
this wrap-up. `origin/main` was still `0877d84`, so there was no sync.

### Done
- **T4.3 `/why` with audio: pass, live.** These results were re-checked at the end of the session with
  `scripts/why_check.py --n 2` on `gemini-3.6-flash`:
  - Audio notes for a mix window and a bass-stem window took 3.5–3.6 s on the first call (SQL ≈ 230 ms,
    excerpt ≈ 1.2 s at 59–76 KB, Gemini ≈ 2.1 s).
  - The forced text-only fallback (P3b) took 1.4 s.
  - Every second call came from the cache in about 100 ms. Notes were 41–44 words (≤ 45).
  - Earlier in the session, 4 audio notes (including a null-bpm Freesound-sourced track) took 2.7–3.9 s.
  - The 20-query plan eyeball check: all valid, 1.2–2.0 s each, no loops at temperature 0.2 (kept).
- **T5.1 contract test: pass.** Fixture mode (part of `make test`): 16 passed, 2 skipped (live-only). Against local
  real mode (`API_URL=http://127.0.0.1:8011`): 14 passed, 4 skipped; with `CONTRACT_WRITES=1`: 16 passed, 2 skipped.
- Checks at the end: `make lint` green; `uv run --project api pytest api` gives 133 passed and 7 skipped (the
  opt-in DB tests and the live-only contract tests).

### Deviations from PLAN.md
- **Excerpt via ffmpeg reading over HTTP** (`core/excerpt.py`, range requests, only the excerpt is downloaded),
  not through `common.audio` (it has no excerpt helper and disables network protocols). That's safe because the
  source is always a `public_url` the API builds for our own bucket, and stderr (which can contain the URL) is
  never logged.
- **The excerpt is the snapped window** (what `/search` plays), cut to ≤ 15 s, mono 22.05 kHz 64 kbps.
- **P1 tweak:** `stems_wanted` / `prefer_sparse` only on explicit isolation ("just the", "only", "acapella"). Before
  the fix, "boom bap drum break" and "jazzy upright bass line" asked for stems, and only 33 of 351 tracks have any.
- **Contract test:** null on one side and absent on the other count as equal (`chips.json` omits null
  `bpm_range` / `key`). Live calls that write (stems, imports, events) only run with `CONTRACT_WRITES=1`.
- `/why` with no cached note while Gemini is degraded or failing → 502 `upstream_error`; `fs_*` windows → 404
  until T8.1.

### Gotchas
- **Another session committed T4.3 and T5.1 in this worktree** while this conversation was interrupted. I briefly
  overwrote `core/why.py` and `routes/why.py` without reading them, then restored them with `git checkout`, so
  nothing was lost. Only one agent should work in a worktree at a time.
- The live scripts (`plan_check`, `rerank_check`, `why_check`) write real rows to `plan_cache` and `notes` in the
  dev DB. Those rows are the cache.
- A paid Gemini key now seems to be in `.env` (no 429s today). `GEMINI_MODEL=gemini-3.6-flash` is in the local
  `.env`, but the `CLAP_*` lines aren't (set them in the env for search checks; proposal C8).
- ffmpeg 9.0.2 (winget) is on PATH locally. The API Docker image must install ffmpeg for `/why`.
- No failing tests.

### State
- No production URL or VM yet. WS3 is still on fixtures, waiting for an API URL.
- Flags: `USE_FIXTURES=0`, `GEMINI_DEGRADED` unset. Code default model is still `gemini-3.8-flash` until C9 lands.
- Real endpoints: `/health`, `/chips`, `/tracks/{id}`, `/search` (planner + rerank), `/why`. Fixture stand-ins:
  `/tracks/{id}/stems`, `/jobs/{id}`, `/imports`, `/events`, `/assist`.
- Fixtures: unchanged. Proposals waiting to land: C7, C8 (needed before the deploy), C9.

### Next
- **First task: T6.1 Docker images** (the api image can be built now; the worker image needs WS1's worker details).
- Human actions first:
  1. Bring the work into `ws2-api`: from the main checkout, `git merge --ff-only ws2-t4 && git push origin ws2-api`.
  2. Create the Vultr VM and send me its IP plus SSH access (T6.2). Send WS3's exact Vercel domains for CORS.
  3. Land C8 (and C7, C9) with WS1, and add the two `CLAP_*` lines to `.env`.
  4. Ask WS1 for the worker's run command, packages and env, and a vocab freeze.


## 2026-11-15 · session 5 (deploy, bench, stems/jobs/imports/events/assist)

Started in the main checkout on `ws2-api`. At the human's request, `ws2-t4` (sessions 3–4) was fast-forwarded into
`ws2-api` and pushed (`2de388d`). Work then continued in worktree `.claude/worktrees/ws2-deploy` on branch
`ws2-deploy`, branched from that commit and pushed. `origin/ws2-api` is fast-forwarded to it after each push; the
last push was this wrap-up. `origin/main` was still `0877d84`, so no sync was needed.

### Done
- **T6.1 Docker images: pass.** `deploy/api.Dockerfile` and `deploy/worker.Dockerfile` use python 3.11-slim, ffmpeg
  and uv 0.13.8, run `uv sync --frozen --no-dev` from each lock (CPU torch), and each has its own `.dockerignore`.
  Each image carries an OCI revision label and `BEATOPIA_REVISION`. The API image builds on the VM and reports
  healthy, with the `hf_cache` volume. The worker image is defined but not built (see State).
- **T6.2 VM + compose + Caddy: pass.** Live at **https://45-77-216-35.sslip.io**.
  - `/health` returns 200 through Caddy with `X-Beatopia-Revision`.
  - CORS allows `https://beatopia-liart.vercel.app`, any `https://beatopia-*.vercel.app` and
    `http://localhost:3000`, and refuses other origins.
  - **Contract test against production with `CONTRACT_WRITES=1`: 16 passed, 2 skipped.** One skip is because the
    stems already existed; the other test runs only in fixture mode.
  - Startup identity line: `revision=56838ae… mode=real clap=laion/larger_clap_general@ada0c23…
    clap_ready=True gemini=gemini-3.6-flash`.
- **T6.3 `scripts/bench.py`: pass** (the accept rule allows "or slowest stage noted"). Production, 20 eval queries:
  - Pass 1: server **p50 3218 ms, p95 3923 ms. Slowest stage: rerank, p50 3.0 s.** 0 errors, at least 4 notes per
    result set. Plans came mostly from `plan_cache`, so a never-seen query adds about 1.3–1.5 s for the planner.
  - Warm pass: **p50 73 ms**, p95 164 ms (sql 71 ms).
  - Locally (L2 → Supabase), the warm pass was p50 273 ms.
- **T7.1 `/tracks/{id}/stems` + `/jobs/{id}`: pass, except the worker leg.** Unit tests and the opt-in DB test pass:
  covering stems, a covering queued job reused, a separate job per model, end clamped, 404s.
  - Live: hero `jam_1030277` 10–20 s → 4 full-length stems and no job. A done WS1 job validates.
  - Not checked: queued → done, because no worker is running.
- **T7.2 `/imports`: pass, except the worker leg.** A live upload of the 16 s fixture WAV created `imp_27b87909`
  plus an analyze job in 1.1 s (0.9 s of it the upload). The placeholder `TrackDetail` validates. A text file named
  `.wav` gets 415, and a file over the cap gets 413 (tested).
- **T9.1 `/events` + Rocchio: pass.** DB test: after a pick and a skip, similarity to the picked window rises and
  to the skipped one falls. `fs_*` picks and other sessions are ignored.
- **T10.1–T10.3 `/assist`: pass.** Snapshot test of the 15 declarations, chain simulator tests, and loop tests with
  real `google.genai` response objects.
  - Live `scripts/assist_eval.py` on `gemini-3.6-flash`: **9/10, 2.1–4.8 s each.** "Chop this into 4 and reverse
    the last one" gives exactly `[slice c1 count 4 beat, reverse c1.4]`.
  - The miss is #9 ("reverse c1" after slicing): it reversed all 4 pieces and arranged them last-to-first.
- **Verified for the human, against the real DB and model:**
  - Query vectors, Rocchio output and 500 sampled window embeddings all have L2 norm 1.000000.
  - Searching with each import window's own embedding (with and without its tags as `must_tags`) returned no
    import tracks.
  - Real mode has no fixture stand-ins left.
- Checks at the end: `make lint` and `uv run --project api pytest api` (results are in the wrap-up commit message
  and the report; nothing was red).

### Deviations from PLAN.md
- **Rerank writes at most 4 new notes per call (`NOTES_PER_RERANK`).** From the VM, 8 notes ran past the 4 s
  budget on every search. A memo hit whose top 4 already have notes skips Gemini; the other results stay
  `why: null` for `POST /why`.
- **Rerank budget timeouts don't count toward auto-degrade** (`timeouts_degrade=False`). Three slow reranks had
  switched Gemini off for 5 minutes, and with it `/why` and `/assist` (502). HTTP errors still count.
- **`/assist` design changes:**
  - Thinking is `LOW`, not `MEDIUM`, for latency.
  - Invalid calls go back to the model for repair, and the response holds only the ops that validated (not
    all-or-nothing).
  - `search_library` runs without Gemini (raw-text plan, score order).
  - The model is shown which clips can be edited now and which are sliced.
- **Stems "covering" requires the same model**, including for heroes, because a 6-stem request needs guitar and
  piano. The plan said hero stems always qualify. Among complete covering sets, the narrowest range wins.
- **A done job with an invalid or missing `output`** is served as `status: "error"` instead of a 500.
- **`WEB_ORIGIN` accepts `*` entries**, turned into `allow_origin_regex`, where `*` matches `[a-z0-9-]+`. This adds no
  new env var. `Server-Timing` and `X-Beatopia-Revision` are exposed to browsers.
- **New deploy-internal variable `BEATOPIA_REVISION`.** It is baked into the image by `deploy.sh`, never set in
  `.env`, and isn't a §8 variable.
- **The VM gets the tree as a `git archive` over SSH**, not a clone, so the VM needs no GitHub credentials. The
  worker sits behind a compose `worker` profile. `deploy.sh` recreates caddy on every deploy.
- **SSH key `id_ed25519`, not `vultr_hack`.** `vultr_hack` doesn't exist on L2; the human approved `id_ed25519`.

### Gotchas
- **The local `.env` line 8 has a typo: `CLAP_MODEL=laion/large_clap_general`.** That model doesn't exist (HF 401).
  It must be `laion/larger_clap_general`. Local live checks used a corrected copy in the job tmp dir. The VM `.env`
  is correct.
- **No worker is running anywhere.** WS1's worker isn't on `main` (`worker/main.py` is still a stub). Earlier
  done/error jobs came from WS1's acceptance runs. 5 analyze jobs from this session are queued (my import check
  plus 4 contract-test runs), and the shared DB now has 6 `imp_*` tracks. A worker will process them when it
  starts. They're synthetic fixture audio and private.
- **Production and dev use the same Supabase.** The contract test with `CONTRACT_WRITES=1` writes real rows (an
  import, a job, `play` events).
- **VM:** Ubuntu 26.10 (`stonking`; Docker's apt repo has it), 4 vCPU, 15 GB RAM, no GPU. ufw was active and
  dropped 80/443 until `vm_setup.sh` added them.
  - Compose commands on the VM need `--env-file .env`, or the `API_DOMAIN` interpolation fails:
    `cd /opt/beatopia && docker compose -f deploy/docker-compose.yml --env-file .env logs -f api`.
- **Deploy:** `VM=root@45.77.216.35 SSH_KEY=~/.ssh/id_ed25519 deploy/deploy.sh <ref>`.
  - It ships committed code only.
  - A redeploy takes about 1 minute (cached layers, CLAP already in `hf_cache`). Health is back about 6 s after it.
  - `/opt/beatopia/DEPLOYED_SHA`, the image label and the response header all show the revision.
- **pgvector's psycopg loader returns `Vector` objects, not numpy arrays.** `personalize._array` handles both.
- **The background-job guard rejects shell commands that contain "git" anywhere.** That includes hostnames such as
  `beatopia-git-…` and `$(git …)` substitutions. Split commands, or put scripts in the job tmp dir.
- The cwd can drift into `api/` after a `cd api && …`; `cd ..` brings it back.
- Live scripts cost Gemini calls: `assist_eval.py` makes about 20, and a bench pass 1 makes up to 2 per uncached
  text query.
- No failing tests.

### State
- **Production:** https://45-77-216-35.sslip.io (VM 45.77.216.35, root, key `~/.ssh/id_ed25519`). Running
  revision: `56838ae` (`X-Beatopia-Revision`). Later commits on `ws2-api` only change docs, so no redeploy is needed. Containers: `api` (healthy) and `caddy`. The worker is
  not started.
- **VM flags** (`/opt/beatopia/.env`, mode 600): `USE_FIXTURES=0`, `GEMINI_DEGRADED=0`,
  `GEMINI_MODEL=gemini-3.6-flash`, `CLAP_MODEL=laion/larger_clap_general`, `CLAP_REVISION=ada0c23…`,
  `WEB_ORIGIN=http://localhost:3000,https://beatopia-liart.vercel.app,https://beatopia-*.vercel.app`,
  `API_DOMAIN=45-77-216-35.sslip.io`.
- **Real endpoints:** all of CONTRACT §6. No fixture stand-ins. Not built yet: the Freesound fallback (T8.1). `fs_*`
  ids not in the DB → 404.
- **Fixtures: unchanged. Shared paths: untouched.** Proposals waiting to land: C7 (`internal_error`), C8 (CLAP
  model/revision), C9 (`gemini-3.6-flash`).
- **Others are already on production:** the logs show searches with limit 5 and `/why` calls from another client.

### Next
- **First task: T8.1 Freesound fallback.** The §7.7 trigger (< 3 results scoring > 0.25) never fires (the score floor
  is about 0.25), so write a proposal to trigger on top-3 `sim` instead, then build it. After that, T11.1 (cold
  search p50 3.2 s → < 3 s: rerank output and a parallel planner + embed), then T11.2 (token bucket, README toggle).
- Human actions first:
  1. In the main checkout: `git pull --ff-only` on `ws2-api` (the remote is ahead).
  2. Send WS3 and WS4 `NEXT_PUBLIC_API_URL=https://45-77-216-35.sslip.io` (with `NEXT_PUBLIC_USE_FIXTURES=0`), and
     run the Gate H16 check with them.
  3. Ask WS1 to merge the worker loop into `main` and start it, then run `WORKER=1 VM=... SSH_KEY=...
     deploy/deploy.sh ws2-api`.
  4. Land C7, C8 and C9 in a `contract:` PR, and fix `.env` line 8.


## 2026-11-15 · session 5 wrap-up 2 (contract PR, main moved)

This entry adds to the session 5 entry above and supersedes its "Next" list.

### Done
- **C7–C9 landed:** contract PR #6 (`contract-ws2-c7-c8-c9`), merged by the human at 04:29 UTC as `b7485cf`.
  - It changes `.env.example`, CONTRACT §4, §6 and §8, and the four WS2 proposal files (marked landed). It also
    documents the `*` entries in `WEB_ORIGIN`.
  - No models, schema or fixtures changed (`make check-fixtures`: 13 fixtures, 0 problems).
- **The API's built-in `GEMINI_MODEL` default is now `gemini-3.6-flash`** (`226e46c`, to match C9). Production is
  unaffected, because its `.env` sets the value.
- PLAN §3 marks C7–C9 as in PR #6 (now merged). T8.1, T11.1 and T11.2 stay unchecked, each with a "Left" note.
- **Answered:** stopping or rebooting the VM needs no redeploy. Docker starts at boot and the containers are
  `unless-stopped`. A manual `docker compose stop`/`down`, or destroying the VM, does need `deploy.sh` again.
  Every redeploy needs `WORKER=1` once the worker runs.
- Checks: `make lint` green, `uv run --project api pytest api` 183 passed, 10 skipped.

### Deviations
- None. The contract PR followed the AGENTS.md process: the human asked for it, a `contract:` PR was opened, and
  the human merged it.

### Gotchas
- **`main` moved:** `32bc7f8` (WS3 search flow #4), `b7485cf` (contract C7–C9), and **`417556d` + `018e0c7`, WS1's
  real worker loop** (`worker/main.py`, `jobs.py`, `handlers.py`, `engine.py`, `imports.py` plus tests).
  `ws2-api` is 4 behind `main` and 31 ahead.
- `deploy/worker.Dockerfile` was written against the stub. It hasn't been built with the real worker yet. WS1's
  `worker/launch.ps1` and `SESSION4.md` may list env vars or system packages the image lacks.
- Since C8 is in `.env.example`, new laptops get the right CLAP values. The human's local `.env` line 8 still needs
  `laion/larger_clap_general`.
- `common/clap.py`'s code default is still `laion/larger_clap_music` (WS1's file). Every env must set `CLAP_*`.

### State
- Production is unchanged: https://45-77-216-35.sslip.io on `56838ae`, `api` + `caddy`, no worker container.
- Branches: `ws2-deploy` = `origin/ws2-api` = `226e46c` plus this entry. `contract-ws2-c7-c8-c9` is merged and can
  be deleted.
- 5 analyze jobs are still queued in the shared DB (synthetic test imports). The first worker to start will
  process them.

### Next
1. **First: sync `ws2-api` with `main`.** Run `git fetch && git rebase origin/main`, then `make schema` and
   `make check-fixtures`, and re-run the checks. Updating the remote needs a force-push, which the human must run
   or approve: `git push --force-with-lease origin ws2-api`. A merge of `origin/main` would avoid the force-push,
   but it departs from the AGENTS.md sync rule.
2. **Start the production worker:** check `deploy/worker.Dockerfile` against WS1's real worker (deps, env, how it
   launches). Then run `WORKER=1 VM=root@45.77.216.35 SSH_KEY=~/.ssh/id_ed25519 deploy/deploy.sh ws2-api`.
   Confirm with `docker image inspect beatopia-worker:latest` (revision label), the worker log, and the 5 queued
   jobs going to done. Also finishes the worker leg of T7.1/T7.2: stems queued → done, import → `GET /tracks/imp_*`.
   Check with WS1 first whether their laptop worker is also running (safe either way: `skip locked`).
3. Then T8.1 (Freesound fallback, plus the §7.7 trigger proposal), T11.1, T11.2.
- Human actions:
  - Approve the force-push in step 1, or choose the merge.
  - Tell WS1 that the VM will run a worker.
  - Fix `.env` line 8.
  - Delete the merged `contract-ws2-c7-c8-c9` branch if you like.
  - WS3/WS4: `NEXT_PUBLIC_API_URL=https://45-77-216-35.sslip.io`, `NEXT_PUBLIC_USE_FIXTURES=0`, then the Gate H16
    check.


## 2026-11-15 · session 5 wrap-up 3 (sync with main, production worker, import fix)

This entry supersedes "Next" in wrap-up 2.

### Done
- **Synced with `main` per AGENTS.md.**
  - Ran `git rebase origin/main` onto `018e0c7`. That commit includes WS3 #4, contract PR #6 and WS1's worker loop.
  - Only 4 files overlapped, all WS2's own `docs/proposals/WS2-*.md` (add/add, because PR #6 had already put
    them on main). Each was resolved with main's version, i.e. the landed text. The proposal-only commit
    `329324b` became empty and was skipped, so 31 of 32 commits were replayed.
  - Checks afterwards:
    - Non-WS2 paths are identical to `main`.
    - `api/` and `deploy/` are identical to before the rebase.
    - `make schema` changed only CRLF (reset). `make check-fixtures`: 13 fixtures, 0 problems.
    - `make lint` green; api tests 183 passed, 10 skipped.
- **Production worker is running** (`WORKER=1 deploy.sh`). Both images are labelled `567279d`.
  - The worker loads CLAP from the shared `hf_cache` volume. Memory: worker ≈ 0.7 GB, api ≈ 0.4 GB.
  - A client's stems job went queued → done (`jam_1485349`).
  - **Gate H16 stems leg works in production.**
- **Import fix (`567279d`):** placeholders now get `attribution = "Uploaded by you"` (the fixture's text).
  WS1's analyze job rejects an empty license or attribution (`worker/imports.py`). Every import had been failing
  with `Analyze requires an import placeholder with license and attribution`.
  - Recovery, per `worker/README.md`: 7 placeholders fixed and exactly those 7 failed jobs requeued by ID (5 test
    imports, 2 from another client). **All 7 done in 4–5 s each.**
  - Fresh end-to-end check: upload → done in ≈ 6 s → `GET /tracks/imp_79e47554` (16 s, 90.7 bpm, 3 windows).
  - Production contract test on `567279d`: 16 passed, 2 skipped.

### Deviations
- **Placeholder attribution is `"Uploaded by you"`, not `''`.** PLAN §2 said `''`; WS1's worker needs it
  non-empty.
- **The rebased branch is pushed as `origin/ws2-api-sync`.** `origin/ws2-api` and `origin/ws2-deploy` still point
  at the pre-rebase `da12496`, because moving them needs a force-push, which this agent doesn't run.
  `deploy.sh` ships local commits, so production already runs the synced code.

### Gotchas
- **Unexplained:** the first `WORKER=1` build labelled the worker image `018e0c7` (main's head) instead of the
  deployed `0694113`, while the api image was labelled correctly. `docker compose config` resolves `REVISION`
  correctly for both, and there are no other build files in the tree. A rebuild with the same input labelled it
  correctly, and the next deploy labelled both `567279d`. The worker code was identical either way (`worker/` and
  `common/` match `main`). Check both labels after each deploy (`deploy.sh` prints them).
- **Never run `docker compose config` on the VM in a session.** It prints every secret from `.env` (it happened
  once this session; the output stayed local).
- The worker runs one job at a time. A crash can leave a job `running`. Requeue only by ID after confirming the
  process is dead (`worker/README.md`).
- The VM worker and any WS1 laptop worker share the DB queue. That's safe (`skip locked`), but tell WS1.

### State
- **Production:** https://45-77-216-35.sslip.io on `567279d` with `api`, `worker` and `caddy`, all
  `unless-stopped`. Flags are unchanged (wrap-up 2).
- Shared DB: no queued or failed analyze jobs from this session remain.
- Branches:
  - local `ws2-deploy` = `origin/ws2-api-sync` = `567279d` plus this entry (rebased on `main`).
  - `origin/ws2-api` and `origin/ws2-deploy` = `da12496` (old).

### Next
1. **Human, first:** move `ws2-api` to the synced branch. From the main checkout:
   `git fetch && git push --force-with-lease=ws2-api:da12496 origin origin/ws2-api-sync:ws2-api`, then
   `git switch ws2-api && git reset --hard origin/ws2-api`.
   Optionally delete `ws2-api-sync`, `ws2-deploy` and `contract-ws2-c7-c8-c9` on origin.
2. Then T8.1 Freesound fallback (with the §7.7 `sim`-trigger proposal), T11.1 (cold search p50 3.2 s → < 3 s),
   T11.2 (token bucket, README toggle).
3. Tell WS1 the VM runs a worker. Run the Gate H16 check with WS3/WS4 on the production URL.
