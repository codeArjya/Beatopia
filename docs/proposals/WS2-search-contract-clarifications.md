# WS2 proposal: search contract clarifications

Covers the Gemini model id, server env vars, private imports, Freesound fallback tracks and score term definitions.

**Author:** WS2 (Search API & AI) · **Status:** proposed, waiting for the human and affected streams ·
**Source:** `api/PLAN.md` §3 (C1–C5)

This file covers all five contract changes from my plan, because they share the same two diffs. Each section
below says why the change is needed, which streams it affects, and whether it can wait. The exact diffs are at
the end. Until a `contract:` PR lands, WS2 builds against the assumption stated in each section.

**What changes:** only `docs/CONTRACT.md` (§6 notes, §7, §8) and `.env.example`. **Nothing changes in
`api/app/models/`, `shared/schema/`, `shared/fixtures/` or `web/lib/types/`**, and no response shape changes, so
`make schema && make check-fixtures` stay clean. Note: `search.json` already has three `source: "freesound"`
results with `fallback_used: false`. Those are stored *library* tracks from WS1's Freesound ingest, which fits this
proposal, so the fixture stays as it is.

| # | Change | Affects | Can wait? |
| --- | --- | --- | --- |
| C1 | `GEMINI_MODEL=gemini-3.8-flash` | WS2 only (human: fix the shared `.env` now) | Yes, until H12 |
| C2 | New env vars `GEMINI_DEGRADED`, `USE_FIXTURES`, `API_DOMAIN`; `WEB_ORIGIN` takes a comma-separated list | WS2 only | Yes, until H12 |
| C3 | Imported tracks are private (excluded from `/search`) | WS3 (UX expectation) | Yes, until H16 |
| C4 | How Freesound fallback tracks behave in `/tracks`, `/why` and stems | WS3, WS4, WS1 | Yes, until the H12 sync (H16 at the latest) |
| C5 | Define `sim`, `tag_overlap` and `bpm_fit` in the score | WS3 (only if it shows scores) | Yes, until H12 |

---

## C1. Gemini model id

**Why.** `.env.example` and CONTRACT §8 say `GEMINI_MODEL=gemini-3.5-flash  # confirm the current Flash id`.
`gemini-3.5-flash` isn't on the official model list I checked on 2026-11-14. The stable Flash models are
`gemini-3.8-flash` (the newest), `gemini-3.6-flash`, `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite`.
`gemini-3.8-flash` supports structured output, function calling, audio input and thinking levels low/medium/high.
**What breaks without it:** anyone who copies `.env.example` gets a model id that may 404 or be silently
re-routed, so the planner, rerank, `/why` and `/assist` all fail or change behavior.

**Affects:** WS2 only (WS2 is the only consumer of `GEMINI_MODEL`). **Human action now:** set
`GEMINI_MODEL=gemini-3.8-flash` in the shared `.env`.

**Can wait until the next gate?** Yes. The code defaults to `gemini-3.8-flash` and the env var overrides it. It
should land by H12 so the production `.env` built from `.env.example` is right.

**Assumption meanwhile:** code default `gemini-3.8-flash`, overridable via `GEMINI_MODEL`.

## C2. New server environment variables

**Why.** The handoff asks for fixture mode behind `USE_FIXTURES=1`, Caddy needs a hostname for HTTPS
(`API_DOMAIN`), and degraded mode needs a manual switch (`GEMINI_DEGRADED`). `WEB_ORIGIN` already accepts a
comma-separated list in `api/app/main.py`, but the contract doesn't say so. **What breaks without it:** nothing
breaks at runtime, because every variable has a safe default. But the variables would be undocumented, so the
production `.env` on the VM could be missing `API_DOMAIN`, Caddy would get no certificate, and the Vercel origin
would be left out of CORS.

**Affects:** WS2 only. `USE_FIXTURES` is server-side and separate from WS3's `NEXT_PUBLIC_USE_FIXTURES`.

**Can wait until the next gate?** Yes. Defaults are `USE_FIXTURES=0`, `GEMINI_DEGRADED=0`, and `API_DOMAIN` unset
(local dev doesn't need it). It's needed by the deploy at H12.

**Assumption meanwhile:** read with those defaults. I'll document them in `api/README.md` and `deploy/README.md`.

## C3. Imported tracks are private

**Why.** `POST /imports` takes a `session_id`, but `tracks` has no owner column. Once the worker analyzes an
upload, its windows would show up in **everyone's** `/search` results. **What breaks without it:** one user's
personal (possibly copyrighted) upload would appear in other users' searches, labeled `license: user-upload`.
That's a licensing problem and bad for the demo.

**Affects:** WS3. Imported tracks are opened by id (`GET /tracks/imp_*` from the `analyze` job output) and never
appear in search results. If WS3 wants a "my imports" list, it should keep the ids client-side (localStorage)
for now. No change for WS1 or WS4. A per-session owner column (`tracks.owner_session`) is a possible later
migration for WS1, but this proposal doesn't ask for it.

**Can wait until the next gate?** Yes. No imports exist before the worker's `analyze` job works (about H10–H12).
It should land by H16, when imports are part of Tier 0.

**Assumption meanwhile:** the search SQL always filters `t.source <> 'import'`.

## C4. Freesound fallback tracks

**Why.** CONTRACT §7.7 says fallback results are "not stored unless picked" but gives no mechanism. Storing them
on `pick` isn't possible as specified: `windows.embedding` is `NOT NULL` (we'd have to run CLAP audio on the
request path), and `notes.window_id` is a foreign key to `windows`. Meanwhile WS3 and WS4 will call
`GET /tracks/fs_*`, `POST /why` and `POST /tracks/fs_*/stems` on these results. **What breaks without it:** clicking
a fallback result in the UI gives a 404 from `/tracks`, a 500 from `/why` (FK violation), and a stems job for a
track the worker can't find.

**The rule (diff below):**
- Fallback results use id `fs_{id}`, window id `fs_{id}:mix:0`, the Freesound `preview-hq-mp3` URL, a
  `0..min(duration, 16)` s window, and `fallback_used = true`.
- `GET /tracks/{id}` checks the DB first. An `fs_*` id that isn't stored is built live from Freesound: one `mix`
  window, `beat_times: []`, `stems: []`, `bpm`/`key` null.
- `POST /why` on such a window works, and its note is cached in API memory only.
- `POST /tracks/{id}/stems` on such a track first stores a minimal `tracks` row (preview copied to Storage
  `tracks/{id}/mix.mp3`, no windows), then enqueues the normal `stems` job.
- A `pick` event only records the event.
- Library Freesound tracks (stored by WS1's ingest, also `fs_*`) are unaffected, because the DB always wins.

**Affects:**
- **WS3:** handle results whose track has `bpm: null` and `key: null`, and treat `fallback_used: true` as a hint
  for a small "from Freesound" label. The license and attribution are always present.
- **WS4:** handle `TrackDetail.beat_times: []`. `snap: "beat"` must fall back to `"transient"`, or to equal parts.
  `stretch_to_bpm` must be disabled or ask for a source bpm when the track bpm is null. WS4 also needs to confirm
  that Freesound preview URLs decode in the browser (CORS). If they don't, I'll write a follow-up proposal to copy
  previews into our Storage bucket on first `GET /tracks/fs_*`.
- **WS1:** the worker must accept a `stems` job for a track that has a `tracks` row but no windows, and read the
  audio from `audio_path` as usual.

**Can wait until the next gate?** Yes, but not past H16. The fallback is built at H15–H16 and is part of the
H16 Tier 0 gate. WS4 needs the `beat_times: []` rule before it finishes slice snapping, so I'd like this landed at
the **H12 sync**.

**Assumption meanwhile:** WS2 implements exactly the rule above.

## C5. Score term definitions

**Why.** CONTRACT §7.4 gives `score = 0.6·sim + 0.2·tag_overlap + 0.1·bpm_fit + 0.1·loopability` but doesn't
define `sim`, `tag_overlap` when there are no must-tags, or `bpm_fit`. The 0.25 fallback threshold depends on
these. **What breaks without it:** nothing crashes, but the score loses its meaning and the threshold can't be
tuned. Text-to-audio CLAP cosine similarities are typically only 0.1–0.4, so with an undefined `sim` the
fallback could fire on almost every query or on none.

**Affects:** WS3, only if it shows `score` (for example as a match percentage). The range stays 0..1, and no
other stream reads the score.

**Can wait until the next gate?** Yes. At H3 I'll measure these definitions on WS1's 20-track seed with the
20 eval queries. If more than 30% of queries fall back, I'll amend this proposal before it lands at H12, rescaling
to `sim = clamp(cos / 0.5, 0, 1)`.

**Assumption meanwhile:** the definitions in the diff.

---

## Exact diffs

### `docs/CONTRACT.md` (§6 notes, §7, §8)

```diff
--- a/docs/CONTRACT.md
+++ b/docs/CONTRACT.md
@@ -408,11 +408,11 @@ Base URL `NEXT_PUBLIC_API_URL`. JSON everywhere except `/imports` (multipart). C
 | `GET /health` | — | `{"ok": true}` | |
 | `GET /chips` | — | `ChipsResponse` | built from `ingest/vocab.txt` + fixed tempo/key chips |
 | `POST /search` | `SearchRequest` | `SearchResponse` | target < 3 s p50 |
-| `GET /tracks/{id}` | — | `TrackDetail` | |
+| `GET /tracks/{id}` | — | `TrackDetail` | DB first; an `fs_*` id not in the DB (Freesound fallback) is built live from Freesound: one `mix` window, `beat_times: []`, `stems: []` |
 | `POST /tracks/{id}/stems` | `StemsRequest` | `StemsResponse` | existing stems covering the range → `stems`; else enqueue job |
 | `GET /jobs/{id}` | — | `Job` | poll every 1 s |
-| `POST /imports` | multipart `file` (≤ 25 MB; wav, mp3, flac, m4a, ogg), field `session_id` | `ImportResponse` | uploads, inserts a placeholder track, enqueues `analyze` |
-| `POST /why` | `WhyRequest` | `WhyResponse` | cached in `notes` |
+| `POST /imports` | multipart `file` (≤ 25 MB; wav, mp3, flac, m4a, ogg), field `session_id` | `ImportResponse` | uploads, inserts a placeholder track, enqueues `analyze`. Imported tracks are private: never returned by `/search`, only by id |
+| `POST /why` | `WhyRequest` | `WhyResponse` | cached in `notes`; fallback windows (not in `windows`) are cached in API memory only |
 | `POST /events` | `EventRequest` | 204 | |
 | `POST /assist` | `AssistRequest` | `AssistResponse` | Gemini function calling over the Op union |
 
@@ -427,12 +427,22 @@ Error codes in use: `not_found`, `bad_request`, `range_too_long`, `clip_is_slice
    Chip filters are merged into the plan deterministically **after** Gemini, so chips always apply.
 2. Query vector `q = embed_text([plan.clap_text])`.
 3. SQL: filter by `must_tags` ⊆ tags (or ≥ 1 overlap if that returns < 10), not `exclude_tags`, bpm range
-   (also accept half/double time), key; stem in `stems_wanted` if given; order by `embedding <=> q`; limit 60.
-4. `score = 0.6·sim + 0.2·tag_overlap + 0.1·bpm_fit + 0.1·loopability` (if `prefer_sparse`: subtract `0.15·density`).
+   (also accept half/double time), key; stem in `stems_wanted` if given; never `source = 'import'`;
+   order by `embedding <=> q`; limit 60.
+4. `score = 0.6·sim + 0.2·tag_overlap + 0.1·bpm_fit + 0.1·loopability` (if `prefer_sparse`: subtract `0.15·density`),
+   clamped to 0..1, where
+   - `sim = clamp(1 − (embedding <=> q), 0, 1)` (cosine similarity);
+   - `tag_overlap = |must_tags ∩ tags| / |must_tags|`, or 0.5 when `must_tags` is empty;
+   - `bpm_fit` = 1 when there is no `bpm_range` or the track bpm (or half/double) is inside it, falling linearly
+     to 0 at 10 bpm outside; 0.5 when the track bpm is null.
 5. Keep at most 3 windows per track; snap to 1/2/4/8/16 bars using beat_times.
 6. Gemini rerank of the top 20 → final `limit`; fill `why` from `notes` cache.
 7. If fewer than 3 results have score > 0.25 → Freesound fallback, normalized into `Result` (`track.source = "freesound"`,
-   id `fs_{id}`, not stored unless picked).
+   id `fs_{id}`, window id `fs_{id}:mix:0`, `audio_url` = Freesound `preview-hq-mp3`, window `0..min(duration, 16)` s,
+   `fallback_used = true`). Fallback tracks are **not stored** in v1 (not even when picked): `GET /tracks/{id}` and
+   `POST /why` serve them live, and a `pick` event only records the event. Exception: `POST /tracks/{id}/stems` on one
+   first stores a minimal `tracks` row (preview copied to `tracks/{id}/mix.mp3`, `bpm`/`key` null, no windows) so
+   the worker can separate it.
 
 ---
 
@@ -444,12 +454,15 @@ DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supaba
 SUPABASE_URL=https://<ref>.supabase.co
 SUPABASE_SERVICE_ROLE_KEY=            # server only, never in web/
 GEMINI_API_KEY=
-GEMINI_MODEL=gemini-3.5-flash         # confirm the current Flash id
+GEMINI_MODEL=gemini-3.8-flash         # newest stable Flash on ai.google.dev as of 2026-11-14
+GEMINI_DEGRADED=0                     # 1 = skip planner/rerank/why/assist generation (Gemini down or rate-limited)
 FREESOUND_API_KEY=
 JAMENDO_CLIENT_ID=                    # optional
 CLAP_MODEL=laion/larger_clap_music
 DEMUCS_MODEL=htdemucs
-WEB_ORIGIN=http://localhost:3000
+WEB_ORIGIN=http://localhost:3000      # comma-separated list of allowed origins
+USE_FIXTURES=0                        # 1 = api answers every endpoint from shared/fixtures (no DB, no CLAP)
+API_DOMAIN=                           # deploy only: Caddy hostname, e.g. 203-0-113-7.sslip.io or api.example.com
 
 # web (Next.js)
 NEXT_PUBLIC_API_URL=http://localhost:8000
```

### `.env.example`

```diff
--- a/.env.example
+++ b/.env.example
@@ -3,12 +3,15 @@ DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supaba
 SUPABASE_URL=https://<ref>.supabase.co
 SUPABASE_SERVICE_ROLE_KEY=            # server only, never in web/
 GEMINI_API_KEY=
-GEMINI_MODEL=gemini-3.5-flash         # confirm the current Flash id
+GEMINI_MODEL=gemini-3.8-flash         # newest stable Flash on ai.google.dev as of 2026-11-14
+GEMINI_DEGRADED=0                     # 1 = skip planner/rerank/why/assist generation (Gemini down or rate-limited)
 FREESOUND_API_KEY=
 JAMENDO_CLIENT_ID=                    # optional
 CLAP_MODEL=laion/larger_clap_music
 DEMUCS_MODEL=htdemucs
-WEB_ORIGIN=http://localhost:3000
+WEB_ORIGIN=http://localhost:3000      # comma-separated list of allowed origins
+USE_FIXTURES=0                        # 1 = api answers every endpoint from shared/fixtures (no DB, no CLAP)
+API_DOMAIN=                           # deploy only: Caddy hostname, e.g. 203-0-113-7.sslip.io or api.example.com
 
 # web (Next.js)
 NEXT_PUBLIC_API_URL=http://localhost:8000
```

### `api/app/models/`, `shared/schema/`, `shared/fixtures/`, `web/lib/types/`

No changes.
