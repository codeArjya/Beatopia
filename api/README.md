# api/ (owner: **WS2**, Search API & AI)

FastAPI service for every CONTRACT §6 endpoint. **`api/app/models/` is the shared contract** (CONTRACT §5): nobody edits
it directly; changes go through `docs/proposals/` and a `contract:` PR.

The bootstrap `app/main.py` answers every endpoint from `shared/fixtures/`, so the frontend works from day one.
WS2 replaces the stubs (keep fixture mode behind `USE_FIXTURES=1`).

```bash
cd api && uv sync && cd .. && make dev-api   # http://localhost:8000/health, /docs
uv run --project api pytest api
```
