# WS2 handoff: Search API, AI orchestration & deploy

**Owner P2 (laptop L2). Branch `ws2-api`.** For the human and the coding agent alike.

## 1. Mission
Own everything between the database and the browser: the FastAPI service, query-time CLAP, scoring, all Gemini
calls (planner, reranker, why notes, `/assist` tool calling), the Freesound fallback, and deployment to Vultr.

**Done when:** every endpoint in CONTRACT §6 is live at the production URL, `/search` p50 < 3 s, responses validate
against the same schema as the fixtures, and `/assist` turns "chop this into 4 and reverse the last one" into valid ops.

## 2. Boundaries
- **Edit only:** `api/` except `api/app/models/` (contract), `deploy/`.
- **Provides:** the HTTP API (CONTRACT §5–7), the production URL, the Vultr VM running `api` + `worker` containers.
- **Consumes:** `common.*` from WS1 (`embed_text`, `db`, `storage`), DB contents from WS1 (seed at H3, full at H12),
  `worker/` code from WS1 for the worker container.
- You own `.env` structure *in practice* (CONTRACT §8); propose any new variable as a contract change.

## 3. Kickoff prompt (paste into the agent)
```text
You are the coding agent for stream WS2 (Search API, AI orchestration & deploy). Read AGENTS.md,
docs/CONTRACT.md and docs/handoff/WS2-api-ai.md fully. Only edit api/ (not api/app/models/) and deploy/.
Do not write code yet. Create api/PLAN.md containing:
1. A final answer for every item in "Decisions" (§5): keep the recommended default unless you find a concrete
   reason not to. Verify the google-genai SDK's current API for structured output and function calling, and the
   current Gemini Flash model id, by reading the installed package or the official docs.
2. "Needs from other streams" and "Contract changes" (each with the assumption you'll use meanwhile).
3. The task list from §6 refined into 1–2 hour checkbox tasks with acceptance checks, mapped to gates H3/H12/H16/H24.
4. Every prompt you will send to Gemini, drafted in full, with its JSON schema.
Then stop and wait for review.
```

## 4. Human setup (once, ~10 min)
```bash
cd sample-app && cp /path/to/.env .env
cd api && uv sync && cd ..
make dev-api            # http://localhost:8000/health and /search should already answer from fixtures
```
Around H10 the agent needs a Vultr VM. Human steps: create the VM in the Vultr console (Ubuntu 24.04; GPU plan if credits
allow, else 4–8 vCPU / 16 GB), add your SSH key, give the agent the IP. Optional: point a GoDaddy domain's A record
at the IP (H32). Everything else (Docker install, compose, Caddy) the agent does over SSH.

## 5. Decisions (recommended defaults; the agent finalizes them in PLAN.md)
| Decision | Recommended default |
| --- | --- |
| Gemini SDK + model | `google-genai`, `generate_content`, model from `GEMINI_MODEL` (current Flash); one client singleton; 10 s timeout, 2 retries with backoff on 429/5xx |
| Planner | Structured output with `SearchPlan` as the response schema; system prompt includes the full tag vocab (so tags are valid) and chip semantics; temperature 0.2; cache in `plan_cache` |
| Chips | Merged into the plan *after* Gemini, deterministically (chip filters always win) |
| Rerank | One call with the top 20 candidates as compact JSON (id, title, tags, bpm, key, stem, score), which returns ordered ids + a ≤ 30-word note for each of the top `limit`; skip rerank entirely if all top 8 already have cached notes |
| Why notes with audio | `POST /why` sends a ≤ 15 s MP3 excerpt inline (well under the 20 MB inline limit) and asks: why does this work as a sample, what to chop, one flip idea. ≤ 45 words, written for a beginner. Cache in `notes` |
| Query CLAP | `common.clap.embed_text`, model loaded at startup (lifespan), CPU is fine |
| Scoring | Exactly CONTRACT §7; weights in `api/app/core/scoring.py` constants; max 3 windows/track |
| Bar snapping | Snap start to the nearest beat, length to 4/8/16 bars at track bpm (1/2 bars for one-shots < 4 s) |
| Fallback | Freesound text search with token auth when < 3 results score > 0.25; map to `Result`; 5 s timeout; cached 1 h |
| Personalization (Tier 2) | Rocchio per session: q' = q + 0.3·mean(picked) − 0.1·mean(skipped), from `events` |
| `/assist` | Gemini function calling; one function per Op type + `search_library(text)` + `get_stems(track_id,start_s,end_s)`; system prompt carries the EditorState JSON and op semantics (CONTRACT §5); validate every returned op with the `Op` union; reject invalid ops with a short reply |
| DB access | psycopg 3 `ConnectionPool` (min 1, max 5) on the session pooler URL; pgvector adapter |
| Deploy | `deploy/docker-compose.yml` with `api`, `worker`, `caddy`; Caddy auto-HTTPS on the domain (or `<ip>.sslip.io` before the domain exists); `restart: unless-stopped`; HF model cache in a named volume |
| Frontend host | Vercel (fast) unless the Vultr prize requires Vultr hosting, then a `web` service in the same compose |
| Observability | One structured log line per request with timings for plan / embed / sql / rerank |

## 6. Build tasks (in order)
1. **Core wiring** (H0–H2): settings from env, DB pool, lifespan CLAP load, error handler returning `{"error": ApiError}`,
   request timing logs. Keep the fixture stubs as fallbacks behind `USE_FIXTURES=1` for local frontend work.
2. **`/chips` + `/tracks/{id}`** (H2–H3): chips from `ingest/vocab.txt` + tempo (70–160 in 10s) + 24 keys.
3. **`/search` v1 without Gemini** (H3–H5): text → CLAP → SQL → score → snap. Test against WS1's 20-track seed.
4. **Gemini planner + cache** (H5–H7), **rerank + notes** (H7–H9), `/why` (H9).
5. **Contract test** (H9): `api/tests/test_contract.py` calls each endpoint and validates it against
   `shared/schema`; fixtures and live responses must have identical shapes.
6. **Deploy** (H10–H12): VM setup over SSH, compose up, HTTPS, CORS for the web origin. **Gate H12: live `/search`.**
   Post the URL to the human for `NEXT_PUBLIC_API_URL`.
7. **`/tracks/{id}/stems`, `/jobs/{id}`, `/imports`** (H12–H15): enqueue jobs for WS1's worker; upload limits and formats.
8. **Freesound fallback** (H15–H16). **Gate H16: Tier 0 end to end in production.**
9. **`/events` + Rocchio** (H16–H19).
10. **`/assist`** (H19–H24): tool registry generated from the Op models, validation, 10 scripted test prompts.
11. **Hardening** (H24–H30): latency pass (parallelize planner + embed where possible), timeouts, graceful
    Gemini-down mode (skip rerank, show cached notes), rate-limit guard.

## 7. Checks
`make lint`, `uv run --project api pytest`, `curl -s $API/health`, plus a latency script (`api/scripts/bench.py`)
that runs the 20 eval queries and prints p50/p95.

## 8. Integration points
- H3: WS1 seed → switch local dev to the real DB. H12: give WS3/WS4 the production URL.
- Response shapes never change without a `contract:` PR; WS3/WS4 rely on the fixtures.
- WS4 sends `EditorState` to `/assist`; your tool descriptions must explain the op semantics in plain words.

## 9. Pitfalls
- Structured-output schemas: keep them flat; tuples (`bpm_range`) may need a two-number array in the Gemini-facing
  schema, then convert back to `SearchPlan`.
- Don't call Gemini per result; one rerank call per search.
- CORS: allow the exact web origin(s), including the Vercel preview domain.
- The transaction pooler (port 6543) breaks prepared statements; use the session pooler URL.
- First request after deploy downloads CLAP weights; warm it in the lifespan and persist the HF cache volume.

## 10. Cut list (first to go)
`/assist` → Rocchio → Freesound fallback → audio in `/why` (text-only notes) → rerank (score order + cached notes).
Never cut: `/search`, `/tracks`, `/chips`, stems endpoints.

## 11. Later prompts
- `Run api/scripts/bench.py against production and fix the slowest stage.`
- `Gemini is rate-limited: switch to degraded mode (cached notes, no rerank) behind a flag and show me how to toggle it.`
- `Redeploy: pull main on the VM, rebuild, run the contract tests against production.`
