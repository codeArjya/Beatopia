# WS1 handoff: Audio data & stems

**Owner P1 (laptop L1). Branch `ws1-data`.** For the human and the coding agent alike.

## 1. Mission
Fill the database with a searchable, licensed sample library and keep stems flowing. Concretely:
- a 300–500 track library, cut into 10 s windows, each with a CLAP embedding, zero-shot tags and audio features;
- ~80 "hero" tracks pre-separated into stems, with stem windows embedded too, so "trumpets" can land on a clean stem;
- a worker that runs on-demand stem separation and import analysis from the `jobs` table.

**Done when:** `/search` (WS2) returns relevant windows for the 20 eval queries, and a 30 s stem job finishes in < 60 s.

## 2. Boundaries
- **Edit only:** `common/`, `ingest/`, `worker/`, `db/migrations/`.
- **Provides:** DB rows per CONTRACT §3, Storage objects per CONTRACT §2, `common` functions per CONTRACT §4
  (WS2 imports `common.clap.embed_text`, `common.db`, `common.storage`), and `ingest/vocab.txt` (also feeds `/chips`).
- **Consumes:** nothing. You are upstream of everyone.
- **The single most important rule:** ingest and the API must use the *same* CLAP model and the same
  normalization. Only `common/clap.py` touches CLAP.

## 3. Kickoff prompt (paste into the agent)
```text
You are the coding agent for stream WS1 (Audio data & stems). Read AGENTS.md, docs/CONTRACT.md and
docs/handoff/WS1-data-stems.md fully. Only edit common/, ingest/, worker/, db/migrations/.
Do not write code yet. Create ingest/PLAN.md containing:
1. A final answer for every item in "Decisions" (§5): keep the recommended default unless you find a concrete
   reason not to, and verify any library/API detail you rely on (package versions, API params) by reading the
   installed package or its docs.
2. "Needs from other streams" and "Contract changes" (each with the assumption you'll use meanwhile).
3. The task list from §6 refined into 1–2 hour checkbox tasks, each with its acceptance check, mapped to gates
   H3 / H8 / H12 / H20.
4. Risks you see, and what you will do if the first ingest run is too slow.
Then stop and wait for review.
```

## 4. Human setup (once, ~10 min)
```bash
cd sample-app && cp /path/to/.env .env
cd common && uv sync && cd ../ingest && uv sync && cd ../worker && uv sync && cd ..
# GPU machines only: install the CUDA torch build per common/README.md
uv run --project ingest python -c "import torch, librosa, demucs; print(torch.__version__, torch.cuda.is_available())"
mkdir -p data   # git-ignored scratch for downloads and stems
```
Then leave the agent alone. You only come back to approve the plan, keep the laptop awake overnight
(`caffeinate -dims` on macOS), and check the seed count at H3.

## 5. Decisions (recommended defaults; the agent finalizes them in PLAN.md)
| Decision | Recommended default |
| --- | --- |
| Sources and counts | Freesound loops/one-shots ~200 (queries from the vocab, `filter=license:("Creative Commons 0" OR "Attribution")`, duration 4–60 s, `previews.preview-hq-mp3`); Jamendo full songs ~150 if `JAMENDO_CLIENT_ID` is set (CC BY / BY-SA only); FMA only if a subset can be fetched without the 7 GB zip; ccMixter/Archive skipped |
| API budget | Freesound: 60 req/min, 2,000 req/day; plan for ≤ 600 requests total and cache every JSON response in `data/cache/` |
| Clip length for long songs | Analyze the first 120 s + one 60 s excerpt from the middle; store mix.mp3 for that 180 s only |
| Windows | 10 s length, 5 s hop, drop windows with RMS below −45 dBFS |
| BPM + beats | `librosa.beat.beat_track` on the full clip; store `beat_times`; null bpm if confidence is low |
| Key | Chroma (CQT) + Krumhansl–Schmuckler template match; store e.g. "A minor" |
| loopability | Mean similarity of onset envelopes between consecutive bars (0..1) |
| density | Spectral flatness + number of stems above −30 dBFS (for hero tracks), scaled 0..1; for non-hero tracks use spectral flatness + onset density |
| CLAP | `laion/larger_clap_music` via transformers `ClapModel`/`ClapProcessor`, 48 kHz input, L2-normalized 512-d output, batch 16 |
| Zero-shot tags | Text prompts `"a recording of {tag}"` per vocab tag, cosine sim; per category keep the top 3 with sim above (category mean + 1 std), store all sims in `tag_scores` |
| Vocab | ~120 tags: instrument ~60 (incl. trumpet, horns, rhodes, piano, strings, flute, sax, guitar, bass, 808, breakbeat, vocal chop, choir, organ, synth pad), genre ~30, mood ~30 |
| Hero tracks | 80 tracks with the highest loopability × tag diversity, at least 30 with prominent horns/keys/strings |
| Stem model | Demucs `htdemucs` (4 stems); `htdemucs_6s` only on request; device cuda → mps → cpu (fall back to cpu if mps errors) |
| Stems storage | MP3 192k at `tracks/{id}/stems/{stem}.mp3`; embed the `other`, `bass`, `drums`, `vocals` windows |
| Worker | One process, poll every 1 s, claim with `for update skip locked`, max range 60 s, writes `progress`; on Demucs failure fall back to python-audio-separator, then librosa HPSS (label stems "harmonic"/"percussive" in `model`) |
| Idempotency | Every step skips work already done (track row exists, windows exist, stems exist) so reruns are safe |

## 6. Build tasks (in order)
1. **common/** (H0–H1.5): `audio.load_mono`, `to_mp3`, `db.connect` (pgvector adapter registered), `storage.upload`,
   `clap.embed_audio/embed_text` (lazy singleton). Test: embed a fixture WAV and the text "drum loop"; cosine > 0.2.
2. **common/analysis.py** (H1.5–H2.5): `analyze_track`, `make_windows`, `zero_shot_tags`. Unit-test on the fixture
   audio (90 bpm ± 2, 3 windows from 16 s).
3. **Freesound source + pipeline, seed run** (H2.5–H3): `ingest/run.py --source freesound --limit 20` → rows +
   Storage. **Gate H3: 20 real tracks in the DB.** Tell the human so WS2 can test real search.
4. **Jamendo source (and FMA if feasible)** (H3–H4); start the full run (`--limit 400`) in the background with
   logging to `data/ingest.log`.
5. **Hero batch** (overnight, during P1's sleep H4–H8): `ingest/run.py --hero 80` → stems + stem windows.
6. **Worker** (H8–H10): `worker/main.py` for `stems` and `analyze` jobs per CONTRACT §3. Test by inserting jobs
   by hand. Time a 30 s CPU separation and report it.
7. **Quality pass** (H10–H12): `ingest/report.py` prints counts per source/tag/license, tag examples, and 10 random
   windows with their top tags; fix bad tags (thresholds, vocab wording). **Gate H12: full library.**
8. **Eval support** (H12–H16): `ingest/eval_queries.yaml` (20 queries, e.g. "dusty soul keys", "solo trumpet", "boom
   bap drums 90 bpm", "melancholy strings", "vocal chop"), plus `ingest/eval.py` that calls `/search` and prints the top 5
   for two humans to grade.
9. **Tier 2 (only after H16):** stem quality checker (bleed via cross-correlation between stems, residual energy, CLAP
   label similarity) that picks the best of two models per job; populate `density` from stem activity for every hero window.

## 7. Checks
`make lint`, `uv run --project ingest pytest`, `uv run --project worker pytest`, `uv run --project ingest python ingest/report.py`.

## 8. Integration points
- H3: tell WS2 the seed is in. H12: tell everyone the full library is in.
- Changing vocab tags after H12 breaks WS3 chips: announce it, and WS2 regenerates `/chips`.
- WS2 deploys the worker container on Vultr from `worker/`; keep `worker/Dockerfile`-friendly entrypoint
  `python -m worker.main` and read config only from env.

## 9. Pitfalls
- CLAP expects 48 kHz; resampling in two places = silently worse search. Only in `common/clap.py`.
- Freesound original downloads need OAuth2; **use previews** (token auth is enough).
- Supabase Storage uploads: set `content-type: audio/mpeg`, and upsert when re-running.
- pgvector: insert numpy arrays via the registered adapter, not strings.
- Demucs on long audio uses lots of RAM; always separate ≤ 180 s chunks.
- Keep `data/` out of git; model weights download to `~/.cache`.

## 10. Cut list (first to go)
FMA → Jamendo (Freesound-only library) → hero count 80 → 40 → stem windows for `drums`/`vocals` (keep `other`) →
Tier 2 quality checker.

## 11. Later prompts
- `Ingest status: report counts, failures from data/ingest.log, and the ETA. Fix any repeating failure.`
- `Run the eval: python ingest/eval.py against $NEXT_PUBLIC_API_URL and save the output to ingest/eval_results.md.`
- `Before I sleep: give yourself a 4-hour task queue (hero batch, then report), run it unattended, log progress.`
