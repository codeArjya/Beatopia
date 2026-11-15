# WS2 PLAN: Search API, AI orchestration & deploy

Branch `ws2-api`. Edits only `api/` (not `api/app/models/`) and `deploy/`.
Status: **reviewed; building.** Synced with the final contract (`cb05f68 contract: typed Job.output, search
fixtures, fallback/import/score rules, env vars`), which adopted proposals C1–C5 unchanged.

Verified on 2026-11-14 against the installed `google-genai==3.3.0` (`api/.venv`) and the official model list
(`ai.google.dev/gemini-api/docs/models`, which now redirects to `aistudio.google.com/docs/models`).

---

## 0. What I verified

**Model id.** The current stable Flash models are `gemini-3.8-flash` (the newest), `gemini-3.6-flash`,
`gemini-3.5-flash-lite` and `gemini-3.1-flash-lite`, plus the preview `gemini-3-flash-preview`. CONTRACT §8 and
`.env.example` now say `GEMINI_MODEL=gemini-3.8-flash`. `gemini-2.5-flash` is deprecated and will be auto-routed
to `gemini-3.5-flash-lite` from 2026-12-01. The `gemini-3.8-flash` model page lists text, image, video, audio and PDF
input, text output, structured outputs and function calling. It accepts thinking levels `low`, `medium` and `high`;
`minimal` returns an error. Limits are 1,048,576 input and 65,536 output tokens.

**SDK surface (read from `google/genai/types.py` and `models.py` in 3.3.0):**

| Need | API |
| --- | --- |
| Client | `genai.Client(api_key=..., http_options=types.HttpOptions(timeout=<ms>, retry_options=types.HttpRetryOptions(attempts=..., initial_delay=..., http_status_codes=[...])))`; async via `client.aio.models.generate_content(...)` |
| Per-call override | `types.GenerateContentConfig(http_options=types.HttpOptions(...))` |
| Structured output | `GenerateContentConfig(response_mime_type="application/json", response_json_schema=<dict>)`; read `response.text`, then `Model.model_validate_json`. `response_json_schema` supports `type, enum, items, prefixItems, minItems, maxItems, minimum, maximum, anyOf, properties, required, additionalProperties, $defs/$ref, description`. `minLength`/`maxLength` are silently not enforced. Schemas that are too large or too deep return `400 INVALID_ARGUMENT`. |
| Function calling | `types.Tool(function_declarations=[types.FunctionDeclaration(name=..., description=..., parameters_json_schema=<dict>)])`; `tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO"\|"ANY"\|"VALIDATED"\|"NONE"))`; `automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)`; read `response.function_calls` (list, can be parallel); answer with `types.Part.from_function_response(name=..., response={...})` |
| Thought signatures | Gemini 3 models return `Part.thought_signature`. On multi-turn tool loops, append `response.candidates[0].content` **unchanged** to the history before the function responses, so the signatures go back to the model. |
| Thinking | `types.ThinkingConfig(thinking_level="LOW"\|"MEDIUM"\|"HIGH")` (`MINIMAL` is rejected by 3.8 Flash) |
| Audio inline | `types.Part.from_bytes(data=mp3_bytes, mime_type="audio/mp3")` |

**Interactions API.** The official docs now mostly show the newer Interactions API (`client.interactions.create`).
`models.generate_content` is still present in 3.3.0 and is not marked deprecated, so I'm keeping it: it is stateless,
which we want, since we resend history anyway. The docs say combining structured output with function calling is
preview-only, so I don't combine them: `/assist` uses function calling and plain text for the reply.

---

## 1. Decisions (final)

| Decision | Final answer |
| --- | --- |
| Gemini SDK + model | Keep the default. `google-genai` `models.generate_content` via `client.aio`, with one client singleton in `api/app/core/gemini.py`. Model = `GEMINI_MODEL`, code default **`gemini-3.8-flash`** (same as CONTRACT §8). Client default: 10 s timeout, `HttpRetryOptions(attempts=3, initial_delay=0.5, max_delay=2, http_status_codes=[429,500,502,503,504])` (= 2 retries with backoff). Search-path calls override this with a tighter budget (planner 4 s / 2 attempts, rerank 4 s / 1 attempt) so `/search` stays under 3 s. Thinking `LOW` for planner, rerank and why; `MEDIUM` for `/assist`. |
| Temperature | Keep 0.2 for planner and rerank, 0.4 for why notes, 0.2 for assist. Google's Gemini 3 guidance prefers the default temperature of 1.0 and warns that low values can cause looping. If the eval queries (task T4.3) show loops or degenerate output, I'll drop the override and use the default. |
| Planner | Keep the default: structured output into a **flat Gemini-facing schema** (`bpm_min`/`bpm_max` instead of the tuple, `key` as an enum, tags as enums from the vocab), then converted to `SearchPlan`. The system prompt carries the full vocab and the chip semantics (prompt P1). Cached in `plan_cache` by `sha256(normalize(text) + "\|" + ",".join(sorted(chip_ids)))`. normalize = lowercase, strip, collapse whitespace. Any Gemini failure or timeout gives `SearchPlan(clap_text=text or chip labels joined)`, and that fallback plan is not cached. If the enum-heavy schema hits `400 INVALID_ARGUMENT`, I'll switch tags to plain strings and filter them to the vocab on the server. |
| Empty text | Chips only: skip Gemini and build `clap_text` from the chip labels, e.g. "trumpet, soul, melancholy music". |
| Chips | Keep the default: merged after Gemini, deterministically. Chip tags are added to `must_tags` and removed from `exclude_tags`. A tempo chip overrides `bpm_range`, and several tempo chips give min(lo)..max(hi). A key chip overrides `key`; if there are several key chips, the last one wins. |
| Rerank | Keep the default. One call with the top 20 as compact JSON (`id,title,tags[:6],bpm,key,stem,score` rounded to 2 dp). It returns the ordered ids plus a ≤ 30-word note for each of the top `limit` (prompt P2). Ids that don't match a candidate are dropped, and any missing ones are appended in score order. New notes are written to `notes` with `model = "<model>:meta"`. Rerank is skipped if the top 8 already have cached notes, if Gemini is in degraded mode, or on timeout (then results stay in score order). |
| Why notes with audio | Keep the default. `POST /why` returns the cached note first. Otherwise it cuts a ≤ 15 s excerpt from the window's `audio_url` (ffmpeg via `common.audio`, mono 64 kbps MP3, ~120 KB) and sends it inline with prompt P3, cached in `notes` (`model = "<model>:audio"`). If the audio fetch fails, the text-only variant P3b runs. Freesound fallback windows aren't in `windows`, and `notes.window_id` is a foreign key, so their notes go in an in-process LRU instead. A cached `:meta` note from the rerank counts as cached, so `/why` doesn't upgrade it. That keeps it to one Gemini call per window. |
| Query CLAP | Keep the default: `common.clap.embed_text`, loaded and warmed in the FastAPI lifespan with one dummy `embed_text(["warmup"])`, on CPU. It runs in `asyncio.to_thread`. Query vectors are LRU-cached by `clap_text` (512 entries). |
| Scoring | CONTRACT §7.4 exactly, with constants in `api/app/core/scoring.py`: `sim = clamp(1 − (embedding <=> q), 0, 1)`; `tag_overlap = \|must ∩ tags\| / \|must\|`, or 0.5 when `must` is empty; `bpm_fit` = 1 with no range or when the bpm (or half/double) is inside it, falling linearly to 0 at 10 BPM outside, 0.5 when the track bpm is null; `loopability` from the row. With `prefer_sparse`, subtract `0.15·density`. Clamp to 0..1. At most 3 windows per track, and windows from the same track that overlap by more than 50% are deduped. `source='import'` tracks are never searched (CONTRACT §6/§7.3). |
| Bar snapping | Keep the default. The start snaps to the nearest beat in `beat_times`. The length is the n in {4, 8, 16} whose `n·4·60/bpm` is closest to the window length. One-shots (track duration < 4 s) use n in {1, 2}. If the end runs past the track, the start moves back by whole beats; if it still doesn't fit, n drops. With no bpm or no beats, the raw window bounds stay and `bars=4` is a nominal value. |
| Fallback | Keep the default. When fewer than 3 results score > 0.25, call Freesound `GET /apiv2/search/text/` with `token=`, `fields=id,name,username,license,duration,previews,url,tags`, `filter=duration:[1 TO 30]`, `page_size=limit`, 5 s timeout, cached 1 h by query. Each sound maps to a `Result`: `id fs_{id}`, `audio_url = previews["preview-hq-mp3"]`, window `0..min(duration, 16)`, and `score = 0.25 + 0.01·(page rank)` capped below the library minimum. Freesound license URLs map to `CC0`, `CC-BY-4.0` or `CC-BY-NC-4.0`, with `attribution = "\"{name}\" by {username} (freesound.org/s/{id})"`. Per CONTRACT §7.7: window id `fs_{id}:mix:0`, `fallback_used = true`, nothing stored (not even on `pick`). `GET /tracks/fs_x` builds a `TrackDetail` live (one `mix` window, `beat_times: []`, `stems: []`) when the DB has no such row. `POST /tracks/fs_x/stems` first stores a minimal `tracks` row (preview copied to `tracks/{id}/mix.mp3`, `bpm`/`key` null, no windows), then enqueues the normal job. |
| Personalization (Tier 2) | Keep the default: Rocchio per session, `q' = normalize(q + 0.3·mean(picked) − 0.1·mean(skipped))`, using events from the last 2 h (max 20 of each), joined to `windows.embedding`. Fallback windows have no embedding and are ignored. It only applies after at least 1 pick. |
| `/assist` | Keep the default with these details. Function calling in `AUTO` mode, automatic calling disabled, a manual loop of at most 3 model turns. 13 op functions (named after `op`, parameters generated from the Op models without `op` and with titles stripped) plus `search_library(text)` and `get_stems(track_id, start_s, end_s)`. The system prompt (P4) carries the op semantics and the EditorState JSON. Every call is checked with `TypeAdapter(Op)` and then a **chain simulator** (`api/app/core/opsim.py`). The simulator tracks the live clip set, rejects unknown clips, `clip_is_sliced` parents, slices with both or neither of `count`/`at`, and `arrange` ids that don't exist. A validation error goes back to the model once as a function response `{"ok": false, "error": ...}`. If the op is still invalid, the response is `ops=[]` with a short reply that explains why. All ops are returned at once, so they form one undo step. |
| `/assist` tool outputs | `AssistResponse` only has `reply` and `ops`. `search_library` returns the top 5 (title, artist, bars, bpm) to the model, which describes them in `reply`. `get_stems` returns stems that already exist, or enqueues a job and tells the model to say "separating, open the Stems drawer". No new response fields are needed. |
| DB access | Keep the default: `psycopg_pool.ConnectionPool(DATABASE_URL, min_size=1, max_size=5, kwargs={"prepare_threshold": None}, configure=register_vector)` in `api/app/core/db.py`. `psycopg[pool]` already comes in through `common`. The pool is opened and closed in the lifespan. Short queries run in `asyncio.to_thread`. |
| Deploy | Keep the default. `deploy/docker-compose.yml` defines `api`, `worker` and `caddy`, all `restart: unless-stopped`. Named volumes: `hf_cache` (→ `/root/.cache/huggingface`, shared by api and worker) and `torch_cache` (Demucs weights). Two Dockerfiles (`deploy/api.Dockerfile`, `deploy/worker.Dockerfile`) start from `python:3.11-slim`, add ffmpeg and uv, and copy `common/` plus the service, using the CPU torch index. If the VM has a GPU, a CUDA variant of the worker image is built with `gpus: all`. Caddy: `{$API_DOMAIN}` → `api:8000`, with `API_DOMAIN=<ip>.sslip.io` until the GoDaddy domain exists. The env comes from `/opt/beatopia/.env` on the VM. |
| Frontend host | Keep the default: Vercel, unless the human confirms the Vultr prize requires Vultr hosting. In that case a `web` service (`next start`) goes into the same compose file behind Caddy on `app.{$API_DOMAIN}`. CORS: `WEB_ORIGIN` takes a comma-separated list, plus an `allow_origin_regex` for `https://<project>-*.vercel.app` previews. |
| Observability | Keep the default. One JSON log line per request: `{path, status, ms, plan_ms, plan_cached, embed_ms, sql_ms, rerank_ms, fallback, n}`. Timings are collected in a contextvar `Timer`. |
| Rate-limit / degraded mode | An in-memory token bucket per `session_id` (search 30/min, why 30/min, assist 10/min) returns `429 rate_limited`. `GEMINI_DEGRADED=1` skips the planner and rerank, and also skips the `/why` and `/assist` generation steps, which return `upstream_error` for missing notes. Three Gemini failures within 60 s turn degraded mode on automatically for 5 minutes. |
| Fixture mode | `USE_FIXTURES=1` (CONTRACT §8) keeps today's stub handlers. Startup then skips CLAP and DB, so the frontend can work with no backend dependencies. |

---

## 2. Needs from other streams

| From | Need | By | Assumption meanwhile |
| --- | --- | --- | --- |
| WS1 | `common.clap.embed_text` implemented, same model as ingest | H3 | Tests monkeypatch it with a deterministic hash → random unit vector |
| WS1 | `common.storage.upload` implemented (`public_url` already works; `pgvector` and `supabase` are now `common` deps) | H12 (imports, stems on fallback tracks) | Tests monkeypatch `upload` |
| WS1 | Seed: 20 tracks with windows, tags from `vocab.txt` exactly, `beat_times` filled | H3 | Local tests use a seeded test schema built from the fixtures |
| WS1 | Full library plus a **vocab freeze** (chips depend on it) | H12 | `/chips` reads `ingest/vocab.txt` at startup |
| WS1 | Worker: processes `stems` and `analyze` jobs per CONTRACT §3, updates `progress`. For `analyze` it **updates the placeholder `tracks` row** I insert (`duration_s`, `bpm`, `key`, `beat_times`, `audio_path`), inserts the windows, and writes `output = {"track": TrackDetail}` | H12 | Placeholder row: `source='import'`, `title=<filename stem>`, `license='user-upload'`, `attribution=''`, `duration_s=0`, `audio_path='imports/{id}/mix.mp3'` |
| WS1 | Worker accepts a `stems` job for a track that has a `tracks` row but no windows (fallback tracks, CONTRACT §7.7) | H16 | As the contract says |
| WS1 | Worker run command and env (`python -m worker.main`, needs ffmpeg, demucs weights, `DEMUCS_MODEL`), so I can write `deploy/worker.Dockerfile` | H10 | As in the Makefile and `worker/pyproject.toml` |
| WS3 | Exact web origins (local, Vercel prod, Vercel preview pattern) | H12 | `http://localhost:3000` plus `https://*.vercel.app` via regex |
| WS3 | Chip ids sent exactly as `/chips` returns them; `POST /why` only when `why` is null; `POST /events` for play/pick/skip/export | H16 | As in the fixtures |
| WS4 | `EditorState` as in CONTRACT §5, with `bpm` filled from the track and ops appended as one undo step | H19 | `assist.json` fixture shape |
| WS4 | Handle `beat_times: []` and `bpm: null` on fallback tracks (beat snap → transient/equal parts; `stretch_to_bpm` disabled) | H16 | CONTRACT §6/§7.7 |
| WS4 | Confirmation that the client can play and decode a Freesound preview URL (CORS) | H16 | Freesound's CDN allows CORS. If it doesn't, I write a proposal (C4b) |
| Human | Vultr VM IP plus SSH access, `GEMINI_API_KEY`, `FREESOUND_API_KEY`, optional domain, whether the Vultr prize requires Vultr hosting for the web app | H10 | `sslip.io` hostname, web app on Vercel |

---

## 3. Contract changes

**Landed** in `cb05f68` (proposal `docs/proposals/WS2-search-contract-clarifications.md`), so these are now
contract and no longer assumptions:

| # | Now in the contract |
| --- | --- |
| C1 | `GEMINI_MODEL=gemini-3.8-flash` (§8) |
| C2 | `GEMINI_DEGRADED`, `USE_FIXTURES`, `API_DOMAIN`; `WEB_ORIGIN` is a comma-separated list (§8) |
| C3 | Imported tracks are private: never returned by `/search`, only by id (§6, §7.3) |
| C4 | Fallback tracks are not stored, served live by `/tracks` and `/why`; stems on one stores a minimal row (§6, §7.7) |
| C5 | `sim`, `tag_overlap`, `bpm_fit` defined, score clamped (§7.4) |

**Open (only if triggered):**

| # | Trigger | Change I'd propose |
| --- | --- | --- |
| C5b | At H3, > 30% of the 20 eval queries fall back on the seed (CLAP text–audio cosine is usually 0.1–0.4) | Rescale `sim = clamp(cos / 0.5, 0, 1)` in §7.4 |
| C4b | WS4 finds Freesound preview URLs don't decode in the browser (CORS) | Copy the preview to `tracks/fs_{id}/mix.mp3` on first `GET /tracks/fs_*` |
| C6 | After the hackathon | `tracks.owner_session text` so imports can be listed per session |
| C7 | **Proposed** (needed now, can land at H12) | `internal_error` (500) in §6 error codes; `docs/proposals/WS2-internal-error-code.md` |
| C9 | **Proposed** (`gemini-3.8-flash` was overloaded and slower; local `.env` has a non-existent model) | `GEMINI_MODEL=gemini-3.6-flash` in `.env.example` / §8; `docs/proposals/WS2-gemini-model.md`. Meanwhile set it in the local `.env` and the deploy env |
| C8 | **Proposed** (needed now: the corpus uses a different CLAP checkpoint than `.env.example`) | `CLAP_MODEL=laion/larger_clap_general` + `CLAP_REVISION=ada0c23…` in `.env.example` / §8; `docs/proposals/WS2-clap-model-env.md`. Meanwhile set both in the local `.env` and the deploy env |

---

## 4. Tasks (1–2 h each, mapped to gates)

Checks after every task: `make lint`, `uv run --project api pytest api`, plus the acceptance check listed.

**Status 2026-11-15 (session 5):** T1.1–T5.1, T7.1, T7.2, T9.1, T10.1–T10.3 done; T6.1–T6.3 done (production at https://45-77-216-35.sslip.io); T8.1, T11.x not started. No fixture stand-ins are left in real mode. T2.2 still
needs one re-check against a seed track (the seed is in the DB now; not re-run yet).

### → Gate H3: real DB wired, chips and tracks real
- [x] **T1.1 Settings, errors, fixture mode** (1 h). *Done:* `create_app(settings)` factory; real mode mounts
      `REAL_ROUTERS` and keeps fixture stand-ins only for endpoints not implemented yet, logging them at startup
      (the list must be empty before T6.2). Unhandled errors → 500 `internal_error` (proposal C7,
      `docs/proposals/WS2-internal-error-code.md`). Tests default to fixture mode via `tests/conftest.py`. `core/settings.py` (pydantic `BaseSettings`-free: plain
      dataclass from `os.environ`, every server variable in CONTRACT §8), `core/errors.py` (move `ApiException`, add `upstream_error`/`rate_limited`
      helpers), `USE_FIXTURES` routes to existing stubs (`app/fixture_routes.py`).
      *Accept:* `USE_FIXTURES=1 pytest` → all `test_stubs.py` pass unchanged; unknown route → `{"error":{"code":"not_found"}}`.
- [x] **T1.2 DB pool + lifespan + timing logs** (1.5 h). `core/db.py` pool, lifespan opens pool and warms CLAP
      (skipped in fixture mode), `core/timing.py` middleware + contextvar timer, JSON log line.
      *Accept:* `make dev-api` with real `.env` → `/health` ok, log line printed with `ms`; startup fails loudly if DB down.
      *Done:* checked against the dev Supabase (pgvector 0.8.2, 7/7 tables). A probe connection runs before the
      pool so a bad URL / missing extension shows the real error. CLAP warm-up logs a warning instead of failing
      while `common.clap.embed_text` is still WS1's stub. Responses carry `Server-Timing` (used by T6.3).
- [x] **T2.1 `/chips`** (1 h). Parse `ingest/vocab.txt` (category headers), ids `inst.|genre.|mood.` +
      slug (`r&b`→`rnb`, `hi-hats`→`hi_hats`, spaces→`_`, as in the fixture), tempo 70–160 step 10 (`bpm_range` ±5), 24 keys (`key.a_minor` → `"A minor"`,
      sharps as `c_sharp_major` → `"C# major"`). Colors `--chip-<category>`.
      *Accept:* response validates `ChipsResponse`; ids for trumpet/soul/tempo.90/key.a_minor equal the fixture's.
      *Done:* the generated response equals `chips.json` exactly (154 chips). Vocab is loaded at startup in real
      mode (bad vocab or duplicate slugs fail loudly); `chip_index()` is ready for the planner merge (T4.1).
- [x] **T2.2 `/tracks/{id}`** (1 h). Join tracks + windows (+ stems) → `TrackDetail`, URLs via `public_url`;
      404 `not_found`. *Accept:* against seed, a seed track validates `TrackDetail`; unknown id → 404 shape.
      *Done:* the WS1 seed isn't in the DB yet (0 tracks), so the SQL is checked by an opt-in integration test
      (`BEATOPIA_DB_TESTS=1`) that inserts a track/windows/stem in one transaction against the dev DB and rolls
      back. Windows are ordered mix first, then by stem and start. Real mode now also requires `SUPABASE_URL`.
      Re-check against the seed at H3. The `fs_*` live fallback is T8.1.

### → toward Gate H12: live `/search` in production
- [x] **T3.1 Search SQL + scoring** (2 h). `core/search_sql.py` (must ⊆ tags, relax to overlap if < 10, exclude,
      bpm incl. half/double, key, stems, `source <> 'import'`, order by `<=>`, limit 60), `core/scoring.py`
      (constants + per-track cap + overlap dedupe). *Accept:* unit tests for score math & caps; seed query
      "dusty soul keys" returns ≤ 8 results, ≤ 3 per track, scores in 0..1.
      *Done:* live on the WS1 seed (350 tracks, ~6.5k windows) with `CLAP_MODEL=laion/larger_clap_general` @
      `ada0c23…` (WS1's model, see C8): 8 results, max 3 per track, scores 0.54–0.58, all Rhodes/R&B/soul windows.
      Warm SQL 80–170 ms round trip (39 ms in Postgres, exact top-N sort, no ANN index needed at this size).
      Null-bpm tracks pass a bpm filter (bpm_fit 0.5, §7.4). Dedupe drops same track + same stem windows that
      overlap ≥ 50% of the shorter one (the plan said > 50%; adjacent 10 s / 5 s-hop windows overlap exactly 50%).
      DB test uses temp tables that shadow the real ones inside a rolled-back transaction.
- [x] **T3.2 Bar snapping + Result mapping** (1.5 h). `core/snap.py`; stem windows use `tracks/{id}/stems/{stem}.mp3`.
      *Accept:* unit tests (90 bpm → 4 bars = 10.667 s; one-shot → 1/2 bars; end clamp); `/search` v1 (no Gemini)
      validates `SearchResponse` on seed, p50 < 1 s locally. Record the fallback rate of the 20 eval queries
      (> 30% → write proposal C5b).
      *Done:* `scripts/search_check.py` (in process, real DB + CLAP) over the 20 queries in `scripts/eval_queries.py`:
      all 200 and valid against `SearchResponse` and `shared/schema`. **p50 297 ms / p95 388 ms** uncached
      (embed ≈ 100 ms, SQL 140–340 ms through the session pooler), p50 160 ms with cached query vectors.
      **Fallback rate 0/20**, so C5b is not triggered. But note for T8.1: even "kazoo orchestra" tops out at 0.52,
      because the non-sim terms give a floor of ≈ 0.25 (tags 0.1 + bpm 0.1 + loopability), so the §7.7 trigger
      (< 3 results > 0.25) will practically never fire. T8.1 needs a trigger on `sim` instead → proposal then.
      v1 plan = raw text (or chip labels + " music"), chips merged by `core/planner.py` (T4.1 adds Gemini in front).
      Empty text with no chips, or an unknown chip id → 400 `bad_request`; CLAP not loaded → 502 `upstream_error`.
      Snap: when nothing fits (sound shorter than 1 bar) the raw bounds stay with `bars=1`.
- [x] **T4.1 Gemini client + planner + cache** (2 h). `core/gemini.py` (singleton, retries, degraded switch),
      `core/planner.py` (P1, flat schema → `SearchPlan`, chip merge, `plan_cache`).
      *Accept:* recorded-response unit tests (mock client) for merge rules; live: "sad trumpet around 90 bpm,
      no drums" → must_tags ⊇ {trumpet}, exclude ⊇ {drum loop|kick|snare...}, bpm ≈ [85, 95]; 2nd call hits cache (< 50 ms).
      *Done:* live on `gemini-3.6-flash` (see C9): the trumpet query → `must [trumpet]`, exclude the 6 drum tags,
      bpm (85, 95), 1.5 s; 2nd call 0.1 ms (in-process LRU), fresh process 100 ms (`plan_cache` row).
      `scripts/plan_check.py` is the live check. Changes from §1: tags are plain strings in the Gemini schema (two
      126-value enums → `400 INVALID_ARGUMENT`), filtered to the vocab server-side; thinking `MINIMAL` (LOW took
      3–11 s; sent as LOW to 3.8 Flash, which rejects MINIMAL); budgets are wall-clock (the API rejects HTTP
      deadlines < 10 s); auto-degrade (3 failures / 60 s → 5 min) landed now instead of T11.2.
- [x] **T4.2 Rerank + notes** (1.5 h). `core/rerank.py` (P2), notes cache read/write, skip rules.
      *Accept:* mock test: hallucinated ids dropped, missing ids appended; live: top 8 get `why`, rerank_ms logged.
      *Done:* live (`scripts/rerank_check.py`, `gemini-3.6-flash`): "dusty soul keys" and the trumpet query got 8/8
      notes, rerank 2.3–3.3 s; the repeat search is `skipped:memo` in 219 ms (no Gemini call). Added an in-process
      **order memo** (request + chips + limit + top-20 ids → Gemini's order): the score-order top 8 rarely equals
      the reranked set, so the "top 8 cached" skip alone would re-call Gemini on every repeat. Free-tier key hits
      `429 quota` after a few calls/minute; those searches fall back to score order + cached notes as designed.
      **Open for T11.1:** uncached search = 2.8–5.3 s total (rerank output is the slow part), over the 3 s p50.
- [x] **T4.3 `/why` with audio** (1.5 h). Excerpt via ffmpeg, P3 / P3b fallback, cache.
      *Accept:* live note ≤ 45 words, 2nd call cached; text-only path covered by a test with audio fetch forced to fail.
      Run the 20 eval queries once and eyeball plans (temperature check from §1).
      *Done:* live (`scripts/why_check.py`, `gemini-3.6-flash`, paid key): 4 audio notes (mix, 2 drum stems, a
      null-bpm Freesound track) 39–43 words in 2.7–3.9 s (excerpt ≈ 1.1 s via ffmpeg HTTP seek, 60–95 KB mono
      64 kbps; Gemini 1.5–2.3 s, thinking MINIMAL); forced text-only P3b 1.9 s; every 2nd call cached ≈ 100 ms.
      The excerpt is the *snapped* window (what `/search` plays), ≤ 15 s. Stored as `<model>:audio|text`, first
      writer wins. No cached note + Gemini degraded/failing → 502 `upstream_error`; `fs_*` not in DB → 404 until T8.1.
      **Eyeball (20 eval queries, fresh):** all valid, 1.2–2.0 s each, no loops at temperature 0.2 (kept). Fix:
      P1 put `stems_wanted` + `prefer_sparse` on "boom bap drum break" / "jazzy upright bass line"; only 33 of 351
      tracks have stems, so P1 now asks for a stem only on explicit isolation ("just the", "only", "acapella").
      Remaining quirks (left as is): 3 must_tags on "lo-fi piano with vinyl crackle" (the relax step covers it);
      the acapella query expands exclude_tags to bass/piano/guitar.
- [x] **T5.1 Contract test** (1 h). `tests/test_contract.py`: every endpoint, live (`API_URL` env) or TestClient,
      validated against `shared/schema/api.schema.json` with `jsonschema`, and key sets compared to fixtures.
      *Accept:* passes in fixture mode and against local real mode.
      *Done:* fixture mode (in `make test`) 16 passed / 2 live-only skipped; local real mode
      (`API_URL=http://127.0.0.1:8011`) 14 passed / 4 skipped, and with `CONTRACT_WRITES=1` 16 passed / 2 skipped.
      Every 2xx body is checked against the schema + the Pydantic model, plus a recursive key-set compare with the
      fixture (list items paired by `op`/`kind`/`category`). A key that is null on one side and absent on the other
      counts as equal: `chips.json` omits null `bpm_range`/`key` in chip filters, the API serializes them as null.
      Error bodies must be `{"error": ApiError}` (404 route/job/track/window, 400 body, `range_too_long`).
      Live, stems/imports/events only run with `CONTRACT_WRITES=1` (they create jobs/rows once T7.x/T9.1 land).
      Re-run against production at T6.2.
- [x] **T6.1 Docker images** (1.5 h). `deploy/api.Dockerfile`, `deploy/worker.Dockerfile`, `.dockerignore`.
      *Accept:* both build locally (or on the VM); `docker run api` → `/health` ok with HF cache volume.
      *Done (files, session 5):* both Dockerfiles (python 3.11 slim, ffmpeg, uv `sync --frozen --no-dev`, CPU torch
      from each lock), per-Dockerfile `.dockerignore`s, OCI revision label + `BEATOPIA_REVISION` from the
      `REVISION` build arg. Built on the VM (Ubuntu 26.10, 4 vCPU / 15 GB, no GPU); `/health` healthy with the
      `hf_cache` volume. The worker image is defined but not built yet: WS1's `worker/main.py` is still a stub on
      main, so compose keeps it behind the `worker` profile (`WORKER=1 deploy/deploy.sh` once WS1 lands it).
- [x] **T6.2 VM + compose + Caddy** (2 h, needs human: VM IP). SSH: install Docker, clone repo to `/opt/beatopia`,
      copy `.env`, `docker compose up -d`, Caddy HTTPS on `<ip>.sslip.io`, CORS origins.
      *Accept:* `curl https://<host>/health` ok; `/search` from the Vercel origin passes CORS; contract test green
      against production. **Gate H12: post the URL to the human for `NEXT_PUBLIC_API_URL`.**
      *Done (files):* `docker-compose.yml` (api, worker profile, caddy; hf/torch/caddy volumes), `Caddyfile`,
      `vm_setup.sh`, `deploy.sh` (git archive over SSH, no GitHub access on the VM), `vm.env.template` (C8/C9 values,
      `WEB_ORIGIN` incl. `https://beatopia-*.vercel.app`, which the API turns into an origin regex).
      *Done:* live at **https://45-77-216-35.sslip.io** (SSH with `id_ed25519`, human-approved). `vm_setup.sh`
      (Docker 29.9 + compose v5.7 from Docker's repo, 4 GB swap, ufw 22/80/443; ufw had been dropping 80/443),
      `/opt/beatopia/.env` from `vm.env.template` values, `deploy.sh`. Identity line: `revision=<sha> mode=real
      clap=laion/larger_clap_general@ada0c23… clap_ready=True gemini=gemini-3.6-flash`; every response carries
      `X-Beatopia-Revision`. CORS: prod Vercel, `beatopia-*.vercel.app` previews and localhost allowed, others not.
      Contract test against production (`CONTRACT_WRITES=1`): 16 passed, 2 skipped. Fixes found in production:
      rerank timeouts tripped auto-degrade (→ /assist, /why 502) — fixed by a 4-note cap + budget timeouts no longer
      degrading; Caddy probe 5 s; `deploy.sh` recreates caddy (bind mount follows the swapped tree).
- [x] **T6.3 `api/scripts/bench.py`** (0.5 h). 20 eval queries (mix of text-only, chips-only, text+chips), prints
      p50/p95 per stage from the timing headers (`Server-Timing`). *Accept:* prod p50 < 3 s, or slowest stage noted.
      *Done (script):* local real mode, pass 1 p50 560 ms / p95 4.8 s (rerank at its 4 s budget on 4 text queries),
      warm pass p50 273 ms (slowest: sql 267 ms via the session pooler).
      *Production (`2fa509d`):* pass 1 server p50 **3218 ms** / p95 3923 ms, **slowest stage rerank (p50 3.0 s)**,
      0 errors, every result set has ≥ 4 notes; plans came mostly from `plan_cache`, so a never-seen query adds the
      planner (≈ 1.3–1.5 s). Warm pass p50 **73 ms** / p95 164 ms (sql 71 ms; VM ↔ Supabase is faster than L2).
      Over 3 s on cold queries → T11.1 (rerank output size / parallel planner + embed).

### → Gate H16: Tier 0 end to end in production
- [x] **T7.1 `/tracks/{id}/stems` + `/jobs/{id}`** (1.5 h). Covering stems = same track, `range_start ≤ start` and
      `range_end ≥ end`, model match (hero full-length stems always qualify); dedupe identical queued/running job;
      range checks (`range_too_long`, `bad_request`). *Accept:* tests for covered / queued / dedupe / > 60 s;
      with WS1 worker running, a job goes queued → done and returns `Stem` list.
      *Done:* `core/jobs.py`: one complete stem set for the requested model whose range covers the request
      (narrowest wins; model must match, since a 6-stem request needs guitar/piano), else a covering queued/running
      job, else a new one; per-track advisory lock; end clamped to the track length. A done job with an invalid or
      missing output is reported as `status: error`. Live: hero `jam_1030277` 10–20 s → 4 full-length stems, a done
      WS1 job validates. *Left (WS1):* queued → done needs a running worker; none is running (session 5 log).
- [x] **T7.2 `/imports`** (1.5 h). ≤ 25 MB streamed check (`upload_too_large` 413), ext + magic sniff
      (`unsupported_format` 415), id `imp_{8 hex}`, upload `imports/{id}/original.{ext}`, placeholder row, `analyze` job.
      *Accept:* tests for size/format errors; live upload → job done → `GET /tracks/imp_x` validates.
      *Done:* live upload of the 16 s fixture WAV → `imp_27b87909` + queued analyze job in 1.1 s (upload 0.9 s); the
      placeholder track validates; a text file named .wav → 415. *Left (WS1):* job → done needs the worker.
- [ ] **T8.1 Freesound fallback** (1.5 h). `core/freesound.py` (httpx, 5 s, 1 h TTL cache, license mapping),
      `/tracks/fs_*` and `/why` for non-DB ids (in-memory note cache), `POST /tracks/fs_*/stems` stores the minimal
      row + copies the preview first (CONTRACT §7.7). *Accept:* mock-HTTP tests; live nonsense query
      "kazoo orchestra" → `fallback_used: true`, results validate, attribution present; `pick` writes no track row.
      *Left:* all of it; the §7.7 trigger (< 3 scores > 0.25) never fires on the seed (score floor ≈ 0.25), so trigger on `sim` + proposal.
      **Gate H16: search → preview → stems → editor works in production (checked with WS3/WS4).**

### → Gate H24: `/assist`
- [x] **T9.1 `/events` + Rocchio** (1.5 h). Insert event (204); `core/personalize.py`; applied in `/search` when
      session has picks. *Accept:* test: after a pick, the picked window's track ranks ≥ before; event row exists.
      *Done:* DB test: after pick + skip, sim to the picked window rises and to the skipped one falls; fs_* picks and
      other sessions are ignored; rows exist. Log fields `picks`/`skips`.
- [x] **T10.1 Tool registry** (1.5 h). `core/assist_tools.py`: function declarations generated from Op models
      (strip `op`/titles, `anyOf[null]` → optional), descriptions from §5 P4 table. *Accept:* snapshot test of
      the 15 declarations; each schema accepted by a live `count_tokens`/dry call.
- [x] **T10.2 Chain simulator** (1.5 h). `core/opsim.py`: live clip set, slice children, `clip_is_sliced`,
      arrange ids. *Accept:* unit tests incl. "slice c1 then gain c1" → `clip_is_sliced`.
- [x] **T10.3 `/assist` loop** (2 h). P4, manual function-calling loop (≤ 3 turns, thought signatures preserved),
      validation → one repair round → reply. *Accept:* `tests/assist_eval.py` with the 10 scripted prompts in §5;
      live ≥ 9/10 produce exactly the expected ops; "chop this into 4 and reverse the last one" →
      `[slice c1 count 4 snap beat, reverse c1.4]`. **Gate H24.**
      *Done:* `scripts/assist_eval.py` live on `gemini-3.6-flash`: **9/10**, 2.1–4.8 s each; case 1 exactly as above.
      The miss (#9 "reverse c1" after slicing) reversed all 4 pieces and arranged them last-to-first instead of
      asking. Changes from §1: thinking LOW (not MEDIUM, latency); invalid calls are sent back to the model for repair
      and only the valid chain is returned (not all-or-nothing); `search_library` runs without Gemini (fast).

### H24–H30: hardening
- [ ] **T11.1 Latency pass** (1.5 h): speculatively `embed_text(raw text)` in parallel with the planner, use it if
      `plan.clap_text` == raw text; parallel rerank + notes fetch; bench before/after.
      *Left:* all; main target is rerank (2.3–3.3 s, uncached search 2.8–5.3 s); auto-degrade already done (T4.1).
- [ ] **T11.2 Timeouts, degraded mode, rate limits** (1.5 h): token bucket, auto-degrade, `GEMINI_DEGRADED` toggle
      documented in `api/README.md`. *Accept:* tests with mocked Gemini 503s → `/search` still 200 with cached notes.

Cut order (from handoff): `/assist` → Rocchio → Freesound fallback → audio in `/why` → rerank.

---

## 5. Gemini prompts (full drafts)

Placeholders in `{braces}` are filled by the server; `{VOCAB_*}` comes from `ingest/vocab.txt` at startup.

### P1. Search planner

Config: `response_mime_type="application/json"`, `response_json_schema=PLAN_SCHEMA`, `temperature=0.2`,
`thinking_level=LOW`, timeout 4 s, 2 attempts.

System instruction:
```text
You turn a music producer's search request into a search plan for a library of Creative Commons
music, cut into short windows (about 4 to 16 bars). Each window is tagged automatically with tags from a
fixed vocabulary and matched against your "clap_text" with a CLAP audio-text embedding model.

Write the plan so the right windows come back:

clap_text: one short English description of how the sound should SOUND, as a caption for an audio clip
  (for example "a melancholy solo trumpet over soft jazz chords, slow tempo"). Describe instruments,
  timbre, mood, genre and texture. Do not include BPM numbers, keys, artist names, song titles, or words
  like "sample", "loop" or "find me". Under 25 words.
must_tags: tags the window MUST have. Use only tags from the vocabulary below. Add a tag only when the
  user clearly asks for it (an instrument they name, a genre they name). Prefer 0 to 2 tags; when in
  doubt, put the idea in clap_text instead. Never put moods in must_tags unless the user insists.
exclude_tags: tags the window must NOT have, only when the user says so ("no drums", "without vocals").
  Expand an exclusion to the related tags: "no drums" means drum loop, breakbeat, kick, snare, hi-hats,
  cymbals; "no vocals" means female vocals, male vocals, vocal chop, choir, spoken word, humming.
bpm_min / bpm_max: only if the user mentions tempo. A single number N means N-5 to N+5. "slow" means 60
  to 85, "mid-tempo" 85 to 110, "fast" 120 to 170. Otherwise null.
key: only if the user names a key, written exactly like "A minor" or "F# major" (use sharps, never
  flats: Bb becomes A#). Otherwise null.
stems_wanted: only if the user wants an isolated part: "just the drums" means ["drums"], "acapella"
  or "vocals only" means ["vocals"], "bassline" means ["bass"], "just the horns/keys/melody" means
  ["other"]. Otherwise [].
prefer_sparse: true if the user wants a clean, open, isolated or minimal moment ("clean", "solo",
  "just the", "sparse", "exposed", "breakdown", "intro"). Otherwise false.

The user may also have selected filter chips. Chips are applied by the system AFTER you answer, so do
not repeat them; but do keep clap_text consistent with them (if a "soul" chip is selected, the
description should sound like soul).

If the request is vague ("something cool"), write a reasonable clap_text and leave everything else empty.
If the request is not about music, still return a valid plan with a generic clap_text.

Vocabulary (use these strings exactly):
instruments: {VOCAB_INSTRUMENT}
genres: {VOCAB_GENRE}
moods: {VOCAB_MOOD}
```

User content:
```text
Request: "{text}"
Selected chips: {chip_labels_or_"none"}
```

`PLAN_SCHEMA` (Gemini-facing, flat):
```json
{
  "type": "object",
  "properties": {
    "clap_text":     {"type": "string", "description": "Audio caption, under 25 words."},
    "must_tags":     {"type": "array", "maxItems": 4, "items": {"type": "string", "enum": ["{ALL_VOCAB_TAGS}"]}},
    "exclude_tags":  {"type": "array", "maxItems": 12, "items": {"type": "string", "enum": ["{ALL_VOCAB_TAGS}"]}},
    "bpm_min":       {"type": ["number", "null"], "minimum": 40, "maximum": 240},
    "bpm_max":       {"type": ["number", "null"], "minimum": 40, "maximum": 240},
    "key":           {"type": ["string", "null"], "enum": ["C major","C# major","D major","D# major","E major","F major","F# major","G major","G# major","A major","A# major","B major","C minor","C# minor","D minor","D# minor","E minor","F minor","F# minor","G minor","G# minor","A minor","A# minor","B minor", null]},
    "stems_wanted":  {"type": "array", "items": {"type": "string", "enum": ["vocals","drums","bass","other","guitar","piano"]}},
    "prefer_sparse": {"type": "boolean"}
  },
  "required": ["clap_text","must_tags","exclude_tags","bpm_min","bpm_max","key","stems_wanted","prefer_sparse"],
  "propertyOrdering": ["clap_text","must_tags","exclude_tags","bpm_min","bpm_max","key","stems_wanted","prefer_sparse"]
}
```
Conversion: `bpm_range = (min, max)` if both set (swap if reversed; if only one set, ±5 around it), else `None`.
Tags are filtered to the vocab again server-side (defensive). The key format has to match how WS1 writes `tracks.key`,
which I'll confirm at H3.

### P2. Rerank + notes

Config: JSON schema `RERANK_SCHEMA`, `temperature=0.2`, `thinking_level=LOW`, timeout 4 s, 1 attempt.

System instruction:
```text
You help a beginner music producer pick samples. You get their search request and a list of candidate
windows from a Creative Commons library (already roughly ranked by an audio search model; "score" is
that model's confidence). Each candidate has an id, the track title, auto-detected tags, tempo, key,
which stem it is (mix = full song, or an isolated part) and the score.

1. Return "order": the ids of the {limit} best candidates for this request, best first. Use only ids from
   the list. Favor candidates whose tags clearly match what was asked, prefer isolated stems or sparse
   moments when the user asked for something clean, and avoid putting several windows of the same
   track next to each other. Trust the score when the metadata gives no reason to disagree.
2. Return "notes": for each id in "order" that is listed under needs_note, one note of at most 30 words,
   in plain friendly English for someone new to sampling: why this window could work as a sample for
   this request, and one concrete thing to try (chop on the chord changes, loop 2 bars, pitch it down,
   filter out the low end, and so on). Base it only on the metadata; do not claim things you cannot
   know from it, and do not mention scores or ids.
```

User content:
```text
Request: "{text_or_chip_labels}"
Candidates:
{candidates_json}   # [{"id":"fs_482913:mix:15000","title":"...","tags":["soul","rhodes"],"bpm":92,"key":"A minor","stem":"mix","score":0.61}, ...]
needs_note: {ids_without_cached_note_json}
```

`RERANK_SCHEMA`:
```json
{
  "type": "object",
  "properties": {
    "order": {"type": "array", "items": {"type": "string"}, "maxItems": 24},
    "notes": {"type": "array", "maxItems": 24, "items": {
      "type": "object",
      "properties": {"id": {"type": "string"}, "note": {"type": "string"}},
      "required": ["id", "note"]
    }}
  },
  "required": ["order", "notes"]
}
```
Notes come back as an array of `{id, note}` rather than a map keyed by id, so the schema doesn't need
`additionalProperties`. Notes over 30 words are cut at the last sentence boundary.

### P3. Why note with audio (`/why`)

Config: JSON schema `WHY_SCHEMA`, `temperature=0.4`, `thinking_level=LOW`, client default timeout (10 s, 2 retries).
Contents: `[Part.from_bytes(excerpt_mp3, "audio/mp3"), Part.from_text(user_text)]`.

System instruction:
```text
You are a friendly sampling mentor for producers who are just learning to sample. You will hear a short
excerpt (up to 15 seconds) from a Creative Commons track, plus its title and auto-detected metadata.
Write one note of at most 45 words that covers three things, in this order:
1) why this excerpt works as a sample (what you actually hear: the instrument, the space, the groove,
   the texture);
2) what to chop (where the clean hits or phrases are, for example "the first chord", "each piano hit",
   "the 2-bar horn phrase");
3) one flip idea (reverse, pitch down, slice and re-order, filter, loop).
Use plain words, no jargon without explanation, no hype, and no emojis. Describe what you hear; if the
metadata disagrees with the audio, trust the audio. Do not mention the license or the score.
```

User content:
```text
Title: "{title}" by {artist_or_"unknown artist"}
Stem: {stem}   Tempo: {bpm_or_"unknown"} BPM   Key: {key_or_"unknown"}
Tags: {tags_csv}
Excerpt length: {seconds} s ({bars} bars)
```

**P3b (text-only fallback):** the same system instruction with the first sentence replaced by "You will get the
title and auto-detected metadata of a short excerpt (you cannot hear it)", and the line "Describe what you hear …
trust the audio." replaced by "Base the note only on the metadata and keep claims modest." The user content is
the same, and no audio part is sent.

`WHY_SCHEMA`:
```json
{"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}
```

### P4. Editor assistant (`/assist`)

Config: `tools=[Tool(function_declarations=ASSIST_TOOLS)]`,
`tool_config=FunctionCallingConfig(mode="AUTO")`, `automatic_function_calling=AutomaticFunctionCallingConfig(disable=True)`,
`temperature=0.2`, `thinking_level=MEDIUM`, timeout 10 s. History = `messages` mapped to
`Content(role="user"|"model")`, followed by the loop turns.

System instruction:
```text
You are the assistant inside a browser sample editor for beginner producers. The user describes an edit
in words; you perform it by calling the edit functions. Every function call you make becomes one step
in a non-destructive edit chain that the user can undo all at once.

How the editor works:
- The editor has clips. Each clip plays a range of a source track. Clip ids are "c1", "c2", ...
- Edits are applied in order, on top of earlier edits. Times in trim and slice are in seconds,
  measured from the clip's current start (0 = the start of the clip as it is now).
- slice cuts a clip into pieces named "<clip>.1", "<clip>.2", ... (numbered from 1, left to right).
  "Chop into 4" means slice with count 4. After a clip is sliced you can no longer edit the parent:
  edit the pieces instead ("the last one" of 4 pieces of c1 is c1.4). Slicing a piece again gives
  "c1.4.1", "c1.4.2", ...
- snap "beat" cuts on the track's beats (the default and usually right), "transient" cuts on hits,
  "none" cuts into equal parts.
- repitch changes pitch AND speed together, like a record ("pitch it down", "slow it down like vinyl",
  "chipmunk"). pitch_shift changes pitch only and keeps the length ("change the key", "tune it").
  Semitones: +12 is one octave up, -12 one octave down.
- stretch_to_bpm sets a new tempo. keep_pitch false (default) also changes pitch, like vinyl;
  use keep_pitch true when the user wants the same pitch.
- loop repeats a clip several times where it appears in the arrangement.
- arrange sets the playback order of clips, repeats allowed ("play 1, 1, 3, 2" means
  ["c1.1","c1.1","c1.3","c1.2"]). Without an arrange step the editor plays all leaf clips in order.
- gain is in dB (a little louder is +3, much quieter is -12). Fades are in milliseconds.
  filter highpass removes lows (try 200-400 Hz to remove bass), lowpass removes highs (try 800-2000 Hz
  for a muffled, "underwater" or lo-fi sound).

Rules:
- Only use clip ids that exist in the current editor state (below) or that your own slice calls in
  this turn create.
- If the request is ambiguous about WHICH clip and there is more than one candidate, ask a short
  question instead of guessing. If there is only one clip, use it.
- Use search_library only when the user asks for a different or additional sound; describe what you
  found in one or two sentences (title and why it fits). You cannot add it to the editor yourself:
  tell the user to drag it in from the results.
- Use get_stems only when the user asks to isolate a part (drums, vocals, bass, other).
- If a function returns an error, fix the call once or explain the problem in one sentence.
- After your function calls, reply in at most 2 short sentences: say what you did in plain words and
  suggest one thing to try next. Never invent edits that you did not make with a function call.
- If the user asks for something the editor cannot do (add effects that are not listed, record,
  export), say so briefly and suggest the closest thing it can do.

Current editor state (JSON):
{editor_state_json}

Track info for the clips (JSON): {[{track_id, title, bpm, key, duration_s}]}
```

`ASSIST_TOOLS` (generated from the Op models in T10.1; descriptions written by hand. Shown here as name → description → parameters):

| Function | Description | Parameters (JSON schema `properties`; `required`) |
| --- | --- | --- |
| `trim` | Keep only part of a clip. Times are seconds from the clip's current start. | `clip: string`, `start_s: number`, `end_s: number`; req all |
| `slice` | Chop a clip into pieces named <clip>.1..n. Give count (equal/beat pieces) OR at (cut times in seconds from the clip start), not both. | `clip: string`, `count: integer 2..32`, `at: array<number>`, `snap: enum[beat,transient,none]` (default beat); req `clip` |
| `reverse` | Play a clip backwards. | `clip: string`; req |
| `repitch` | Change pitch and speed together, like a record. Positive = higher and faster. | `clip`, `semitones: number -24..24`; req both |
| `pitch_shift` | Change pitch only, keep the length. | `clip`, `semitones: number -24..24`; req both |
| `stretch_to_bpm` | Change a clip's tempo to target_bpm. keep_pitch=false also changes pitch. | `clip`, `target_bpm: number 40..240`, `keep_pitch: boolean`; req `clip`,`target_bpm` |
| `gain` | Make a clip louder or quieter, in dB. | `clip`, `db: number -36..12`; req both |
| `fade_in` | Fade a clip in over ms milliseconds. | `clip`, `ms: number 0..10000`; req both |
| `fade_out` | Fade a clip out over ms milliseconds. | `clip`, `ms: number 0..10000`; req both |
| `normalize` | Set a clip's peak level (default -1 dB). | `clip`, `peak_db: number`; req `clip` |
| `loop` | Repeat a clip `times` times wherever it plays. | `clip`, `times: integer 1..16`; req both |
| `filter` | Remove lows (highpass) or highs (lowpass) above/below freq_hz. | `clip`, `type: enum[highpass,lowpass]`, `freq_hz: number 20..20000`; req all |
| `arrange` | Set the playback order of clips; repeats allowed. | `order: array<string>` (minItems 1); req |
| `search_library` | Search the sample library for a different or additional sound. Returns up to 5 matches. | `text: string`; req |
| `get_stems` | Isolate parts (vocals, drums, bass, other) of a source range. Returns existing stems or starts a separation job. | `track_id: string`, `start_s: number`, `end_s: number` (max 60 s range); req all |

Every top-level schema is `{"type":"object","properties":{...},"required":[...]}`. Server-side, each op call becomes
`{"op": name, **args}` → `TypeAdapter(Op).validate_python` → simulator. Function responses:
op ok → `{"ok": true, "clips_now": [<live leaf clip ids>]}`; op invalid → `{"ok": false, "error": "<code>: <message>"}`;
search_library → `{"results": [{title, artist, bars, bpm, key, why}]}`; get_stems → `{"status": "ready"|"queued", "stems": [names]}`.

**Scripted eval prompts (T10.3)**, all on one clip `c1` (90 BPM, 10.667 s) unless noted:
1. "chop this into 4 and reverse the last one" → `slice c1 count 4 beat`, `reverse c1.4`
2. "pitch it down 3 semitones like a record" → `repitch c1 -3`
3. "make it 120 bpm but keep the pitch" → `stretch_to_bpm c1 120 keep_pitch true`
4. "slice into 8, then play 1 1 3 2" → `slice c1 count 8`, `arrange [c1.1,c1.1,c1.3,c1.2]`
5. "just keep the first 2 seconds and fade it out" → `trim c1 0 2`, `fade_out c1 ~<=2000`
6. "make it sound muffled and lo-fi" → `filter c1 lowpass 800..2000` (optional `gain`)
7. "loop it 4 times" → `loop c1 4`
8. (state: c1 already sliced into 4) "turn up the third piece" → `gain c1.3 >0`
9. (state: c1 already sliced) "reverse c1" → no ops, reply explains it must target a piece (or asks which)
10. "add some reverb" → no ops, reply says reverb isn't available and suggests the closest edit
