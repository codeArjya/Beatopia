# SETUP.md: from zero to four agents building (about 75 minutes)

Four people, four laptops, one repo. Each person owns one stream and its agent: **P1 = WS1** (data & stems),
**P2 = WS2** (API & AI), **P3 = WS3** (web & search), **P4 = WS4** (editor). All human work is in this file; after Step 5 you mostly prompt agents.

| Step | Who | Time | Result |
| --- | --- | --- | --- |
| 1. Accounts + keys | all four in parallel | 15 min | `.env` filled |
| 2. Laptop installs | each laptop | 15 min (overlaps step 1) | toolchains ready |
| 3. Bootstrap PR | P1's agent; P1 + P2 review (P3 starts Claude Design, P4 checks sponsor rules) | 30–45 min | `main` has scaffold, contract, fixtures |
| 4. Database init | P1 | 5 min | tables + bucket exist |
| 5. Fork into streams | all four laptops | 10 min | four agents planning |
| 6. Plan review | all four | 15 min | four `PLAN.md` approved → build |

**H0 = the moment Step 6 ends.** All gate times in the handoffs are relative to H0.

---

## Step 1: Accounts and keys (split four ways)

| # | Item | Who | How | Goes into |
| --- | --- | --- | --- | --- |
| 1 | GitHub repo `sample-app` (private) | P3 | create empty repo, add all three teammates, protect `main` (require PR) | — |
| 2 | Supabase project | P1 | supabase.com → New project (pick the closest US East region, save the DB password) | — |
| 2a | DB connection string | P1 | Project → Connect → **Session pooler** URI (port 5432). The direct host is IPv6-only and the transaction pooler breaks psycopg prepared statements | `DATABASE_URL` |
| 2b | URL + service role key | P1 | Project Settings → API | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| 3 | Gemini API key | P2 | aistudio.google.com → API keys; note the current Flash model id and free-tier limits | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| 4 | Freesound API key | P1 | freesound.org account → freesound.org/apiv2/apply (instant) | `FREESOUND_API_KEY` |
| 5 | Jamendo client id (optional, for full songs) | P4 | devportal.jamendo.com → create app | `JAMENDO_CLIENT_ID` |
| 6 | Vultr account + hackathon credits | P2 | ask the sponsor table about credits and GPU availability; create account, add SSH key | used by WS2 at ~H10 |
| 7 | Sponsor questions | P4 | at the sponsor tables / Discord: can one project enter several tracks? the rules for Gemini, Vultr, GoDaddy | spec "Prize tracks" checklist |

Put the combined `.env` in a shared password manager or a private DM. **Never commit it.**

## Step 2: Laptop installs

All laptops: `git`, `gh` (logged in), your agent CLI (Claude Code `claude` or Codex `codex`), an editor.

| Laptop | Extra installs |
| --- | --- |
| L1 (WS1) | Python 3.11 + `uv`, `ffmpeg`, ~10 GB free disk, NVIDIA GPU if anyone has one (else CPU/Apple Silicon is fine) |
| L2 (WS2) | Python 3.11 + `uv`, `ffmpeg`, Docker Desktop |
| L3 (WS3) | Node 20+ and `pnpm` (`corepack enable`) |
| L4 (WS4) | Node 20+ and `pnpm`, Chrome (the demo browser) |

Quick check on each: `python3.11 --version; uv --version; ffmpeg -version | head -1; node -v; pnpm -v; docker -v`
(each laptop only needs its own rows).

## Step 3: Bootstrap PR (L1, one agent session)

```bash
gh repo clone <org>/sample-app && cd sample-app
git checkout -b bootstrap
# copy in the kit files: AGENTS.md, CLAUDE.md, docs/CONTRACT.md, docs/SETUP.md, docs/handoff/*.md
cp /path/to/kit/.env .env   # the real one from Step 1
claude          # or: codex
```

Paste this prompt:

```text
Bootstrap this monorepo. Read AGENTS.md and docs/CONTRACT.md first; they are binding.
Create ONLY the scaffold, contract code, fixtures and tooling. Do NOT implement stream features.

1. Layout exactly as CONTRACT §1, with a README.md in each top-level folder saying which stream owns it.
2. Python: separate uv projects in common/, ingest/, worker/, api/ (Python 3.11). ingest, worker and api depend on
   common as an editable path dependency. Install everything listed in AGENTS.md "Stack" in the right project
   (torch CPU build by default; note in common/README.md how to install the CUDA build).
3. api/app/models/api.py and ops.py: copy CONTRACT §5 exactly. api/app/main.py with CORS (WEB_ORIGIN),
   GET /health, and stub routes for every endpoint in CONTRACT §6 that return the matching fixture file, so the
   whole API "works" on fixtures from day one.
4. common/: modules and signatures from CONTRACT §4 with NotImplementedError bodies (except ids.py and
   storage.public_url, which you implement).
5. db/migrations/001_init.sql from CONTRACT §3, plus scripts/db_init.py that applies migrations in order and creates
   the public Storage bucket "audio" if missing.
6. scripts/export_schema.py: Pydantic → shared/schema/api.schema.json; then json-schema-to-typescript →
   web/lib/types/api.ts. scripts/check_fixtures.py validates every shared/fixtures/*.json against the schema.
7. shared/fixtures/: every file in CONTRACT §9 with realistic values (8 search results across 4 fake tracks with
   CC licenses, why notes, tags from a draft vocab). scripts/make_fixture_audio.py generates the synthetic WAVs in
   web/public/fixtures/audio/ (a 90 bpm drum loop + chord pad, 16 s, plus drums/bass/other/vocals stems) with numpy.
8. ingest/vocab.txt: a draft list of ~120 tags grouped by "# instrument", "# genre", "# mood" headers.
9. web/: Next.js App Router + TS strict + Tailwind + shadcn init (add button, card, badge, dialog, sheet, input,
   slider, tabs, tooltip, scroll-area, sonner), install @tanstack/react-query, zustand, @dnd-kit/core,
   @dnd-kit/sortable, wavesurfer.js, tone, vitest. app/layout.tsx with a QueryClientProvider; app/page.tsx and
   app/editor/page.tsx as placeholders. lib/api/client.ts: a typed function per endpoint that returns fixtures
   when NEXT_PUBLIC_USE_FIXTURES=1, else calls NEXT_PUBLIC_API_URL.
10. Makefile targets from AGENTS.md "Commands"; .env.example from CONTRACT §8; .gitignore (.env, .venv,
    node_modules, data/, *.pt, __pycache__); .cursor/rules/ with one .mdc per stream that points to its handoff.
11. Verify: make schema, make check-fixtures, make lint, make test pass; `make dev-api` serves /search from
    fixtures; `make dev-web` renders. Then commit as "chore: bootstrap scaffold and contract" and open a PR.
Report anything in the contract that looked inconsistent instead of silently changing it.
```

P1 and P2 review the PR (10 min: models match the contract, fixtures look sane, `make dev-api` + `make dev-web` run) and merges.

## Step 4: Database init (P1, after merge)

```bash
git checkout main && git pull
cd common && uv sync && cd ..
uv run --project common python scripts/db_init.py
```
Check in the Supabase dashboard: 7 tables exist, the `vector` extension is on, and the public bucket `audio` exists.

## Step 5: Fork into four streams

On each laptop:
```bash
gh repo clone <org>/sample-app && cd sample-app      # L1 already has it
cp /path/to/.env .env
git checkout -b ws<N>-<name>                         # ws1-data | ws2-api | ws3-web | ws4-editor
claude    # or codex
```
Paste the **Kickoff prompt** from that stream's handoff (`docs/handoff/WS<N>-*.md`, section 3). The agent reads
the docs and writes `PLAN.md`, then stops.

## Step 6: Plan review (15 min, all four together)

Read the four `PLAN.md` files side by side and check only three things:
1. Each "Decisions" answer is reasonable (the handoffs give recommended defaults, so this is mostly "yes").
2. "Needs from other streams" lists line up (e.g. WS3's chip assumptions match WS1's vocab plan).
3. Anything marked **contract change**: the affected owners decide now, land one `contract:` PR (any laptop's agent can do it:
   "apply docs/proposals/X.md to the contract, models, schema and fixtures, then open a PR"), and have all
   four branches rebase.

Then tell each agent: `Plan approved. Start building from the first unchecked task. Commit after each task.`

---

## Running the build (your job from here on)

**Gates** (relative to H0; full table in the spec):
| Gate | What must be true | Merge action |
| --- | --- | --- |
| H3 | WS1 seed: 20 real tracks in the DB | — |
| H4 | WS3 app shell + nav + editor route link | merge `ws3-web` → main; WS4 rebases |
| H8 | WS3 search flow on fixtures; WS4 chop/reverse/export on fixture audio | merge both |
| H12 | WS1 full library; WS2 `/search` live on Vultr | merge WS1 → WS2 → set `NEXT_PUBLIC_USE_FIXTURES=0` |
| H16 | **Tier 0 deployed end to end** | tag `v0` |
| H24 | Tier 1 done; `/assist` round-trips | merge all |
| H30 | **Feature freeze** | only `fix:` PRs after this |
| H36 | Submitted | |

**Every ~3 hours, per laptop:** `Sync with main, re-run checks, then continue with the next task in PLAN.md.`

**Prompt cheat sheet**
| Situation | Prompt |
| --- | --- |
| Keep going | `Continue with the next unchecked task in PLAN.md. Commit when its checks pass.` |
| Ready to merge | `Rebase on origin/main, run all checks, push, and open a PR to main titled "<stream>: <summary>" with a short test plan.` |
| Another stream merged | `Sync with main. Then switch from fixtures to the live API for <feature> and fix what breaks.` |
| Behind schedule | `We are behind the <gate> gate. Read the cut list in your handoff, propose what to cut, and wait for my OK.` |
| Contract question | `Write docs/proposals/<WSn>-<topic>.md for this change, keep going with your current assumption, and tell me.` |
| Stuck > 20 min | `Stop. Summarize what you tried, the exact error, and two alternative approaches. Do not change more code.` |
| Before demo | `Run the demo script from the spec against production and list every failure with its cause.` |

**Humans only:** each owner approves their agent's work and reviews one other stream's PRs (P1↔P2, P3↔P4;
cross-pair for `contract:` PRs), decides contract proposals with the affected owners, tries the app in Chrome after
each gate, and sleeps on schedule so two people are always up: P1 + P2 at H4–H8 and H28–H32; P3 + P4 at H8–H12 and
H24–H28. Before sleeping, give your agents long, safe tasks, such as
"finish the remaining ingest batch" or "write tests for lib/audio".
