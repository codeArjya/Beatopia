# Session 3 hero evidence — 2026-11-14

Approved scope: rank/audit hero candidates, benchmark 30/180 seconds, verify a four-stem hero,
start the resumable 80-hero batch. This is the hero task (#5 in the original WS1 handoff),
despite the session prompt's task numbering. Worker claiming/import jobs are still later work.

## Measured inference

Real input: `jam_1030276`, 180-second processed library mix, licensed and published by session 2.
CPU only; Torch 2.15.0+cpu, Demucs 4.1.0; OMP/MKL threads=2; live ingest ran concurrently.
`htdemucs`, split=true, segment=7 s, overlap=0.25, shifts=1, random seed=0.
Checkpoint SHA256: `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.

| Input | Inference | Wall inside benchmark call | Model load (once) | Errors/fallback |
| --- | ---: | ---: | ---: | --- |
| 30 s | 33.183462 s | 33.192235 s | 1.254834 s | None |
| 180 s | 207.197166 s | 207.224432 s | Shared loaded model | None |

These exclude decoding, encoding, embeddings, network I/O and DB publication. No end-to-end worker
<60-second result is claimed. Cold weight download/preflight took 2.019 s in a separate process;
that is not a cold full-pipeline benchmark. Benchmark process uv/Python PIDs 26444/31496 finished.
Raw results: ignored `ingest/data/heroes/benchmarks.json`; stdout/stderr:
`ingest/data/heroes-benchmark-20261114-152209.{stdout,stderr}.log`.
An earlier sandboxed attempt failed reading session-2 cached audio; its logs are retained separately.

## Ranking and thirty-track audit

At 15:20:51 EST, read-only SQL found 98 published candidates. Exactly 95 had selected tags in the
existing horns/keys/strings vocabulary group; 30 were reserved, tag shortfall=0. Ranking uses maximum
mix-window loopability × distinct selected tags / 120; deterministic ID ties. No scores were fabricated
or thresholds relaxed. Snapshot with every candidate, score, exact tags and selected order:
`ingest/data/heroes/audit.json` (batch startup refreshes this file; earlier count is historical).

**Audibly verified qualifying tracks: 0.** This is a tag-based coverage audit, not proof that thirty
tracks have prominent useful horns/keys/strings. All candidates explicitly remain `listening=unreviewed`.
The broader mixed-fixture CLAP semantic check remains failed as recorded in `CLAP_MODEL_REVIEW.md`;
query-time WS2 must still match the approved general CLAP model/revision.

## Publication and recovery semantics

Verified hero: `jam_1121408`, **Jazzi Girl by Marco Margna**, CC-BY-SA-3.0, 180 s processed duration.
Four full stems and **93** real embedded windows: bass=25, drums=33, other=34, vocals=1.
Inference took **169.594342 s**, full pipeline **276.137103 s**; zero failures. A separate read-only
verification passed all expected DB fields/vectors and public hashes. Attributed public audio players
are in ignored `ingest/data/heroes/jam_1121408/listen.html`; audible usefulness remains unreviewed.

The 80-target batch launched at **16:31:16 EST**, uv/Python PIDs **32252/30820**; first new candidate
`jam_1439805`. Refreshed pool=129, tag qualifying=126, reserved=30, tag shortfall=0. Queue=100 distinct
IDs including twenty spares. Frozen thirty-candidate evidence is in `HERO_CANDIDATES_SESSION3.md`.
At 16:31:43 EST SQL: 129 tracks, 3,570 total windows, four stems, one hero, no jobs. Using the first
hero's full wall time, another 79 heroes project to ~6.06 h (~22:35 EST from launch). This is one
sample, not a deadline guarantee. H0 was not supplied; an absolute H12 pass cannot be verified.

Four full-length stereo MP3s, 44.1 kHz / 192k, use unchanged contract paths and processed timelines.
All public hashes must match local decoded MP3s before publication. A single DB transaction writes
four stem rows and their real normalized CLAP windows and then marks the hero. Post-publication
verification checks every expected DB value/vector and public hash. Quiet stems with no searchable
windows fail clearly. No fake vocals, padding windows, alternate models or stem labels are published.

Raw separation survives feature/upload/DB failures. Resume validates source/model/vocab fingerprints,
audio hashes/format/coverage, unique IDs, window bounds, excerpt joins and normalized vectors. Hero
and ingest locks are independent. Queue selection freezes at batch start; twenty ranked spares can
replace failed candidates without lowering the requested completion count. A failed attempt still
produces a nonzero final exit. ETA excludes fast cached verifications.

Stem-window density uses measured stem activity. Existing mix-window density remains unchanged
for compatibility with concurrent ingest verification; completing hero mix density is still the
explicit later density task. `report.py` remains assigned to the later quality pass; current counts
come from read-only SQL (`launch-heroes.ps1 -Mode status -Foreground`).

## Tests

Final 16:36:41 EST SQL snapshot: **142 tracks / 4,071 windows / 8 stems / 2 heroes**, no jobs.
Batch verified **2/80**, zero failure events, next `jam_1436572` separating. New hero `jam_1439805`
has 94 windows; inference=194.708918 s, full pipeline=303.476473 s. Existing `jam_1121408` verified
in 1.724493 s without inference/publication. Latest remaining ETA=22,604.929 s (~6 h 17 m), projected
finish ~22:53 EST from two actual new-publication timings. This supersedes the initial one-sample ETA.

- Focused hero suite: **19 passed in 23.32 s** (first version: 16 passed in 28.07 s).
- Final ingest suite: **44 passed in 46.21 s**; previous pass 35.58 s; earlier version: 41 passed in 48.42 s.
- Final worker suite: **1 passed in 0.02 s**.
- Python Ruff check and format-check: pass across common/ingest/worker/api/scripts, final output 45 files.
- `make lint`: attempted repeatedly, Make command unavailable. Global web lint is unverified.
- No shared helpers changed; common suite was not rerun for this session.
- Initial worker invocation from repo root mistakenly collected unrelated projects and failed with
  four import/collection errors (`fastapi`, `ingest` absent in worker environment). Corrected to run
  from `worker/` with `uv run --project . pytest`; no dependencies or other-stream code changed.
- Pytest used unique workspace basetemps, workspace UV cache and the cached FFmpeg PATH.

Final publication counts, processes, ETA and next-session commands are recorded in
`docs/codex-handoff.md` after the live verification checkpoint.
