# api/ (owner: **WS2**, Search API & AI)

FastAPI service for every CONTRACT §6 endpoint. **`api/app/models/` is the shared contract** (CONTRACT §5): nobody edits
it directly; changes go through `docs/proposals/` and a `contract:` PR.

The bootstrap `app/main.py` answers every endpoint from `shared/fixtures/`, so the frontend works from day one.
WS2 replaces the stubs (keep fixture mode behind `USE_FIXTURES=1`).

```bash
cd api && uv sync && cd .. && make dev-api   # http://localhost:8000/health, /docs
uv run --project api pytest api
```

## Degraded mode (Gemini down or rate-limited)

Gemini is optional on every path. When it's off, the API keeps answering:

| Endpoint | With Gemini off |
| --- | --- |
| `POST /search` | raw-text plan (chips still apply), CLAP + SQL score order, cached notes in `why` (others `null`) |
| `POST /why` | cached notes as usual; a window without one → 502 `upstream_error` (the UI shows no note) |
| `POST /assist` | 502 `upstream_error` ("the editing assistant is unavailable right now") |
| everything else | unaffected |

It switches on in two ways:
- **Automatically:** 3 failed Gemini calls (HTTP errors, bad JSON, timeouts except rerank's own 4 s budget) within
  60 s → Gemini is skipped for 5 minutes, then retried. The log says `gemini auto-degraded for 300 s`.
- **By hand:** `GEMINI_DEGRADED=1` (CONTRACT §8), fixed for the life of the process.

Toggle it in production (VM `45.77.216.35`, ~40 s of 503s while CLAP warms up):

```bash
ssh -i ~/.ssh/id_ed25519 root@45.77.216.35
cd /opt/beatopia
sed -i 's/^GEMINI_DEGRADED=.*/GEMINI_DEGRADED=1/' .env          # back on: GEMINI_DEGRADED=0
docker compose -f deploy/docker-compose.yml --env-file .env up -d --no-deps --force-recreate api
docker compose -f deploy/docker-compose.yml --env-file .env logs --tail 20 api | grep -i gemini
```

The startup log then shows `gemini off: GEMINI_DEGRADED=1`. Locally: `GEMINI_DEGRADED=1 make dev-api`. Don't run
`docker compose config` on the VM: it prints every secret in `.env`.

## Rate limits

In-memory token buckets (`app/core/ratelimit.py`, one process). Over the limit → 429
`{"error": {"code": "rate_limited", ...}}` with a `Retry-After` header (seconds).

| Endpoint | Key | Sustained | Burst |
| --- | --- | --- | --- |
| `POST /search` | `session_id` | 30 / min | 20 |
| `POST /why` | client IP (last `X-Forwarded-For` hop, set by Caddy) | 120 / min | 40 |
| `POST /assist` | client IP | 20 / min | 10 |

`/why` and `/assist` requests carry no session id (CONTRACT §5), hence the IP. The limits are generous enough for a demo
room sharing one Wi-Fi NAT; change `LIMITS` in `ratelimit.py` if they bite. A restart resets every bucket.
