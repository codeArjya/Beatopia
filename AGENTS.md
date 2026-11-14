# AGENTS.md: rules for every coding agent in this repo

Claude Code reads this through `CLAUDE.md`, Codex reads it directly, and Cursor through `.cursor/rules/`.

## Product in one paragraph
A sample-discovery app for newer producers learning to sample. Smart search (text + stackable category chips) over
a curated, pre-indexed Creative Commons library → preview the suggested 4–16 bar window → optional stem
separation → chop/join/reverse/repitch in a browser editor → WAV export. Every result has a short Gemini-written
"why this works as a sample" note. Built in ~37 hours at HackUMass by four people, each running one agent on their own laptop.

## Read these first
1. `docs/CONTRACT.md`: shared types, endpoints, DB, storage, op chain semantics. **Binding.**
2. `docs/handoff/WS<N>-*.md`: your stream's guide.
3. Your stream's `PLAN.md` once it exists.

## Streams and the only paths each may edit
| Stream | Paths |
| --- | --- |
| WS1 Audio data & stems | `common/`, `ingest/`, `worker/`, `db/migrations/` |
| WS2 Search API & AI | `api/` except `api/app/models/`, `deploy/` |
| WS3 Web shell & search UX | `web/` except `web/app/editor/`, `web/components/editor/`, `web/lib/audio/`, `web/stores/` |
| WS4 Editor & audio engine | `web/app/editor/`, `web/components/editor/`, `web/lib/audio/`, `web/stores/` |

**Shared (contract) paths, nobody edits them directly:** `docs/CONTRACT.md`, `api/app/models/`, `shared/`,
`AGENTS.md`, `CLAUDE.md`, `Makefile`, `.env.example`, `web/lib/types/`.
If you need a change there, write `docs/proposals/<WSn>-<topic>.md` (what, why, exact diff) and tell the human.
Keep working with your current assumption until the human lands a `contract:` PR.

If a task seems to need a file outside your paths, **stop and ask the human** instead of editing it.

## Workflow
- First session: produce `PLAN.md` in your stream's main folder (see the handoff), then stop for review.
- Work in small, reviewable commits on your stream branch (`ws1-data`, `ws2-api`, `ws3-web`, `ws4-editor`).
  Conventional prefixes: `feat(ws3): ...`, `fix(ws1): ...`. Mark dependency additions `[dep]`.
- After every task: run the stream's checks (listed in the handoff) and update the checkbox in `PLAN.md`.
- When asked to "sync": `git fetch && git rebase origin/main`, then `make schema && make check-fixtures`, resolve
  conflicts only inside your own paths, re-run checks.
- Never commit secrets. `.env` is git-ignored; only `.env.example` is committed.
- Never block on another stream: code against `shared/fixtures/` and the contract.

## Stack (installed by the bootstrap; don't swap libraries without a proposal)
- Web: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui, pnpm, TanStack Query, Zustand, dnd-kit,
  wavesurfer.js v7 (+ Regions, Timeline), Tone.js, Vitest.
- Python 3.11, uv, FastAPI, Pydantic v2, psycopg 3 + pgvector, supabase-py, librosa, transformers + torch (CLAP),
  demucs 4.1 (maintained fork `adefossez/demucs`), google-genai, httpx, pytest, ruff.
- Data: Supabase Postgres (pgvector) + Storage bucket `audio`. Hosting: Vultr VM (api + worker), web on Vercel or Vultr.

## Commands
```bash
make schema            # Pydantic → shared/schema/*.json → web/lib/types/*.ts
make check-fixtures    # validate shared/fixtures against schema
make dev-api           # uvicorn on :8000
make dev-worker        # job worker
make dev-web           # next dev on :3000
make test              # pytest + vitest
make lint              # ruff + eslint + tsc --noEmit
```

## Conventions
- Python: type hints everywhere, ruff-clean, no global state except model singletons loaded once.
- TS: strict mode, no `any` on API data (use generated types), components small, server state via TanStack Query,
  editor state via Zustand only.
- Audio: 44.1 kHz everywhere in the browser; CLAP gets 48 kHz (common/clap.py resamples).
- Licenses: every track carries `license` + `attribution`; the UI always shows them.
- Prefer boring, working code over clever code. The demo must survive hackathon Wi-Fi.
