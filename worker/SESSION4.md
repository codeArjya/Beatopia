# Session 4 acceptance evidence

2026-11-14, branch `ws1-data`, starting commit `0877d84`. Human approved the plan before code.
Scope: refined plan rows 7–8 (worker; original WS1 handoff task #6). No dependencies, migrations,
API/schema/signature changes, ID changes, storage-contract changes, or common helper changes.

## Verified acceptance

| Check | Recorded evidence |
| --- | --- |
| Competing claims | Two real DB clients targeting one queued job: exactly one claim. Both initial and final live runs passed. |
| Skip locked | Another connection held the queued row lock; claim returned no job, then claimed after release. |
| No long-held claim transaction | A separate connection acquired the job row `FOR UPDATE NOWAIT` during processing. Claim connection closes before inference. |
| Session locking | Real `pg_locks`/`pg_stat_activity` inspection found the held worker advisory lock with null `xact_start`. |
| Progress/status | Separate connection saw running progress 0.4; subsequent 0.2 did not regress it. Error retained partial progress/null output. Successful jobs ended done/1.0. |
| Error termination | Real reversed-range, >60-second and malformed-analyze jobs reached error/null output. Deliberate handler failure did too. |
| Valid range output | Real `fs_166649` [5,35] job produced all four htdemucs stems, validated against the original Pydantic `StemsJobOutput`. |
| Storage/audio | Public bytes matched each locally encoded MP3 hash; files decoded as finite audio, stereo 44.1 kHz, 192k encode, duration 30 seconds. |
| Absolute/local offsets | Metadata [5,35], filenames `*_5000_35000.mp3`, file-local zero. A request [10,20] reused those files; track time 10 maps to local 5. Offline two-tone crop independently verified the requested source region. |
| Import | Hand-inserted analyze job updated `imp_16158261` placeholder, retained title/artist/license/attribution, published `imports/imp_16158261/mix.mp3`. Actual analysis/CLAP, no mocked scores. |
| Import windows/output | 16-second synthetic fixture produced [0,10], [5,15], [10,16], three unit-normalized 512-D vectors with real tags. Pydantic `AnalyzeJobOutput` passed; 90.6661 BPM/A minor were measured. |
| Reuse/recovery | Live repeat import retained three windows/hash and reused analysis. Live covering stem repeat skipped inference. Offline tests cover upload/DB failure resume, corrupt public audio, incomplete stem sets, corrupt derived vectors, and changed-identity refusal. |

Import indexing does not authorize public search: `source='import'` remains unchanged and CONTRACT §6–7
requires WS2 to exclude it. API/browser behavior is not verified by these direct worker checks.

## Real timings

Cached model files, two OMP/MKL threads; Torch 2.15.0+cpu, Demucs 4.1.0. CUDA=false, MPS=false.
No GPU was available, so no GPU result is claimed. These are individual observations, not p50 estimates.

| Job | Handler + terminal DB (s) | Enqueue → claim → processing → terminal poll (s) |
| --- | ---: | ---: |
| Initial 16 s synthetic import | 76.122924 | 77.591679 |
| Repeat import, analysis reused | 6.125295 | 7.516235 |
| Uncached real 30 s four-stem job | **46.208013** | **47.608574** |
| Covering [10,20] repeat | 3.864264 | 5.282667 |
| Post-review [10.001,20.001] covering regression | 4.056200 | 5.731500 |

The **single CPU 30-second observation passed <60 s**. It includes mix download/decode, model loading,
inference, raw checkpointing, four encodes, uploads/public verification, DB publication, progress and
terminal polling. Python/module startup before enqueue and queue backlog are excluded. The initial
import loaded CLAP in the same process beforehand; Demucs was first loaded for this stem job.
Background hero work continued during this session. Model files were already cached; no cold-download
or deployment/GPU latency is claimed.

30-second job breakdown: download/decode 0.445249 s; Demucs load 0.408206 s (parameter hashing follows
and is included in total); inference 29.384854 s; CPU fallback=null. Split=true, 7 s segments,
overlap=.25, shifts=1, seed=0. Model parameter SHA256:
`bd6946ef7ef52d7cc02168913f8776174a6c4b8f861c22b274fdfe8833a3a91b`.
Source mix SHA256 `28236387c66c30feab401f97c3f03381d3001037f467ffb944968d845a236aa6`.

Success job IDs:

- Import: `c059acf6-1753-45a5-9323-30f150c410ec`.
- Repeat import: `d1eff4f9-5a00-4151-a22a-4a9682e7ea92`.
- 30 s stems: `843be018-1f71-4c94-9361-b3c298360f0b`.
- Covering repeat: `c66a0ddf-db4b-4c76-8554-9e108d3d2712`.
- Post-review covering regression: `7241eb22-802c-490b-b392-c4943ed71598`.

Seven expected error audit rows remain, not operational worker failures:
`6f6623b3-35f6-4e82-88f7-46f4d5f557e9`, `b6578779-67c4-4ea8-806b-6bb034ee0fdf`,
`09c36510-c540-4040-a58d-82cc3dfab312`, `e622c072-9226-4fa0-8a74-77d10a529661`,
`f445b330-4e1f-48ff-9c85-d46ee0fe0747`, `f1e55735-ffb5-4c13-a59b-65d2e1a0e501`,
`28f0ce2c-e627-4544-a921-7b189ecc260b`.

## Checks

- First task: worker **14 passed/20.94 s**; ingest **44 passed/37.46 s**; first live DB suite
  **2 passed/10.83 s**. Python Ruff check/format passed, then 49 files.
- Import task: worker **22 passed, 2 skipped/69.52 s**; ingest **44 passed/46.87 s**.
- Final product-code checks: worker **23 passed, 5 skipped/31.03 s**; ingest **44 passed/41.04 s**.
  The five skipped tests require opt-in DB access and separately passed: **5 passed/22.69 s**.
  All skips are explicit live DB tests, not weakened assertions.
- Commands: `uv run --project worker pytest worker/tests` and `uv run --project ingest pytest ingest/tests`,
  with FFmpeg PATH, workspace UV cache, two OMP/MKL threads, `-q -p no:cacheprovider --tb=short`, fresh
  basetemps `worker/data/pytest-task8-final` and `ingest/data/pytest-task8-final`.
- Live: `WORKER_LIVE_TESTS=1 uv run --project worker --env-file .env pytest worker/tests/test_jobs_live.py
  -q -s -p no:cacheprovider --tb=short --basetemp=worker/data/pytest-task8-live`.
- `make lint` attempted after both tasks and final review: Make absent. Direct
  `uv run --project api ruff check common ingest worker api scripts` and matching
  `ruff format --check` pass (**54 files**, including the ignored local diagnostic script).
  Web checks were not run; no global lint pass claimed.
- Common helpers unchanged; common suite not rerun. `ingest/report.py` remains absent and deferred;
  count snapshots use read-only DB queries through the existing hero status command.
- Initial live tests were sandbox-blocked before DB insertion; escalated reruns passed. Initial
  protected cache decode failed; escalated read-only diagnosis passed. No ACLs or dependencies changed.
- Unrelated schema hash remains
  `BB8F20C0BA862279A7B89B12C3E2946AF087E43F10E1AE184132AC2E181F6DF5`; never staged.

## Existing pipeline failures investigated read-only

Unchanged -45 dBFS gate is linear RMS 0.0056234133. Rejected mixes' actual decoded full-clip RMS:
`fs_507355` 0.0049312245 (6.48535 s), `fs_498604` 0.0021100365 (51.37837 s),
`fs_498606` 0.0013835818 (58.60420 s). Existing log locations are `pipeline.py:128:prepare`
(no audible windows). Full RMS alone does not characterize every individual window.

Rejected hero decoded stems' maximum **any sliding 4-second** RMS:

- `jam_1307441`: vocals 0.0041934609.
- `jam_1149165`: bass 0.0015662981, vocals 0.0018476197.
- `jam_1149164`: bass 0.0002242316, vocals 0.0001773818.

These measured quiet stems support the existing `heroes.py:164:features` no-audible-window rejection;
other stems have louder sections. No silence threshold, score, fingerprint or checkpoint was changed.
Read-only diagnostic is preserved locally as `worker/data/inspect-session4.py`.

## Limits and next work

Actual six-source weights/inference, GPU timing, deployed latency, live API/browser integration and
listening quality are unverified. Six-source naming/output and CPU retry behavior are unit tested.
Contract filenames/PKs cannot hold multiple model variants for identical coverage; a conflicting
model/range filename fails explicitly instead of replacing an existing published object.

Worker imports keep full uploaded timelines. Library excerpt joins and existing full-hero windows
remain unchanged. On-demand range stems are not added as overlapping search windows. Fingerprints
and raw checkpoints survive retries. Crashed running jobs require explicit recovery after confirming
the owner is dead; no automatic lease/timeout/schema change was introduced.

Continue with reporting/quality audit and vocabulary calibration, then query evaluation per the
human's Session 5 scope. Keep mixed-fixture CLAP >0.2 failure, listening/30-prominent-timbre gate,
hero target 80, completed mix-density work and API integration separately open.
