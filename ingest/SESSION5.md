# Session 5 evidence and remaining acceptance

2026-11-14, `ws1-data`, starting commit `437f86e`. Human approved the plan before implementation.
Scope is refined plan rows 9–10, both part of original WS1 quality-pass task #7. Implementation is
reviewable; full quality acceptance is **not complete**. Both plan checkboxes remain open.

## Verified corpus audit

Final complete audit snapshot **18:31:41 EST / 23:31:41 UTC**, finished **18:33:11 EST**, 90.938 s.
Source: `ingest/data/session5/report-reviewed.json`; SHA256
`40a44567512aec9046ea4b93ab0bff3ec0b15024cbd56b81e740a3876ec658c7`.
Committed summary: `REPORT_SESSION5.json`, including every tag count, top example IDs, ten random
windows with metadata/tags, verified track IDs, per-object public hashes, missing stages and errors.

| Measure | Verified result |
| --- | --- |
| Library | **350 tracks: 200 Freesound + 150 Jamendo** |
| Excluded from library | One synthetic Session-4 acceptance import, `imp_16158261` |
| Complete technical heroes | **24/80**, 56 short |
| Windows | **7,777 total**, 7,774 library + 3 import |
| Window stems | mix=5,222 (5,219 library), bass=611, drums=717, other=783, vocals=444 |
| Stem rows | **100**, comprising 96 full-hero and four on-demand range rows |
| Public library objects | **450/450** decoded/probed successfully |
| Hash anchors | **446** match local expected hashes; four range files have public hashes without a local anchor in this reporter |
| Stream format | All 450: one MP3 audio stream, 44,100 Hz, two channels, 192,000 bit/s |
| Invalid windows / cache-DB mismatches / public failures | **0 / 0 / 0** |
| Jobs | done=5, error=7; no queued/running jobs; all seven errors are exact intentional Session-4 acceptance IDs |
| Audibly verified prominent timbres | **0; unreviewed**, not inferred from tags |
| Identified human track/stem listening reviews | **1**, jam_1282782 other; exact-window/formal prominence rating incomplete |

Licenses, excluding the import: Freesound BY-3.0=28, BY-4.0=98, CC0=74; Jamendo BY-3.0=34,
BY-SA-3.0=116. Exact versions, source URLs and attributions match cached source metadata. License
eligibility is checked using the existing URL rules; no legal interpretation or new license was invented.
DB durations, BPM, key, beats, window vectors/features/tags and expected full-stem rows were compared
against cached manifests/arrays. The public bytes themselves were decoded completely and probed.
This verifies technical playback and integrity, not browser playback or musical usefulness.

The report takes a repeatable-read, read-only snapshot, closes its DB connection, then checks artifacts
and public audio with four bounded HTTP callers. A later hero can finish after that snapshot. Missing
queued entries are shown separately: 50 unpublished mix candidates include unused queue spares and
rejections; the 100-entry hero queue also includes 20 spares. Neither is a count of corrupt published files.
Historical failures remain visible even when the current library passes its technical count gate.

Earlier full runs: initial report verified 350 mixes/19 heroes/430 objects; intermediate report at
18:05:35 EST verified 350/20/434 in 75.422 s; 18:17:56 EST verified 350/21/438 in 93.890 s.
The final reviewed snapshot supersedes their counts and incorporates the identified human review.

## Explicit cuts and gates

Session 5 audited the **24 complete heroes available at its final full snapshot**, rather than claiming
80 were present. The operating batch still targets **80**; it was never stopped, restarted or reduced.
The 30 prominent-timbre gate is unverified. No acceptance requirement was weakened or checked off.
H0 is unknown, so no absolute H12 timing pass is asserted. The real <60 s CPU job evidence remains
Session 4's single measured observation; no new speed/GPU/deployed/API result is claimed here.

Full quality acceptance also needs reviewed sparse/dense examples, useful instrument prominence and
live integration. The existing mixed-fixture CLAP >0.2 semantic failure remains open. Numerical tags,
successful decoding and repeatable outputs do not establish these judgments.

## Cached tag replay and frozen mapping

`calibrate.py` recomputed tags from **7,249 cached audio embeddings**, covering all 350 library mixes
plus the 19 heroes from the initial audit. It did not rerun audio embedding/separation, modify DB rows,
rewrite manifests or invalidate running-job fingerprints. Selected tags were identical; maximum score
delta was **4.6193599700927734e-7**, below the explicit 1e-5 replay comparison tolerance. This tolerance
does not change the actual tag selection threshold. No affected rows needed a migration.

Final replay timestamp **18:17:38 EST**. Full local output `ingest/data/session5/calibration.json`,
SHA256 `a410fe07fdcebb777019fafea4f8041aec0e9a96bdd1594086d7a33d8faf4cde`.
Committed examples, quantiles and decode diagnostics: `CALIBRATION_SESSION5.json`. The source audit
time/hash is recorded there; it intentionally differs from the later 24-hero report snapshot.

Forty-eight attributed auditions include ten seed-5 random windows from the initial audit, low/high
mix/other density proxy extremes, three score-selected examples each for horns/keys/strings and one
prominent-timbre candidate for each of those 19 heroes. All are explicitly **listening=unreviewed**.
Playable page: `ingest/data/session5/calibration.html`; it bounds playback to the processed-track window.
Browser playback was not exercised by this session. Tests check metadata escaping and playback bounds.
The human later supplied listening feedback for **`jam_1282782/stems/other.mp3`**: horns/low tones, strings, piano, electric guitar,
saxophone and basic synth; uncertain trumpet/bongos; a denser but distinguishable arrangement with a
useful beginning/guitar section. Exact wording is preserved in `listening-session5.json`. This counts
as **one identified track/stem listening review**; the exact time window and a formal prominence judgment
were not supplied. The reporter matches it to a technically verified hero, deduplicates track credit,
and keeps the 30-prominent-timbre gate open. No ten-second label or tuning result is invented.

Measured examples show why listening calibration stays open:

| Window | Existing density proxy | Independent observation |
| --- | ---: | --- |
| `jam_1149160:mix:145000` | ~7.37e-13 | Decoded mono RMS 0.864693; four stems exceed -30 dBFS. Near-zero onset proxy does not prove a simple arrangement. |
| `jam_1047157:other:70000` | 0.000003068 | Active-stem fraction 0; spectral flatness ~0.000006136. |
| `jam_1464239:other:130000` | 0.501337 | Active-stem fraction 1; spectral flatness ~0.002674934. |

Chunk-local onset measurements use different normalization/boundary context from full-excerpt analysis;
they are diagnostics, not replacements for stored feature values. Hero stem-window density is activity
based; **hero mix-window density still uses the original onset proxy**. Completing all hero mix densities
is the original later required task, with cache/DB consistency and live-process coordination required.
No speculative threshold or prompt change was justified without reviewed listening evidence.

`vocab-freeze.json` records **60 instruments, 30 genres, 30 moods**, all existing raw-tag/chip mappings,
the prompt `a recording of {tag}` and per-category stable top-three selection strictly above mean plus
one population standard deviation. Vocab SHA256:
`58e11a8e9df70520508d5a902d7120d3aa42a133d09f690c8306f70534b6ed9c`.
Fixture SHA256: `7fb1d16f7040073fde601f4ba8c377ccab10333b0dabe5f073f6098b9220bc75`.
CLAP remains `laion/larger_clap_general`, revision `ada0c23a36c4e8582805bb38fec3905903f18b41`.
The human explicitly replied **“Both streams have agreed”** for WS2/WS3 preserving this mapping;
confirmation recorded at 18:15:54 EST. No external messages were sent. Calibration checks the frozen
mapping/model before replay and fails clearly on drift. `vocab.txt` itself is byte-for-byte unchanged.

## Failure investigation

Original mix ingest finished at 350 completed / 3 rejected / 353 attempted / 400 queued. Three unique
failures appear as six historical log events because `fs_507355` was retried in prior sessions. Rejected
mixes' measured max sliding-four-second RMS: fs_498604=0.0050529595, fs_498606=0.0050121027,
fs_507355=0.0051131967. Gate remains **0.0056234133**, linear RMS (-45 dBFS).

Real rejected stem audio was decoded read-only; complete measurements are in the calibration evidence.
Examples of maximum sliding-four-second RMS:

- jam_1348228 drums=0.0005550786, vocals=0.0001913616.
- jam_1359980 vocals=0.0018207307.
- jam_1149159 vocals=0.0002304711.
- jam_1238674 vocals=0.0051187798.
- jam_1149161 vocals=0.0007518567.

The diagnostic also measures actual nominal 10 s / 5 s-hop windows and terminal windows with the
recorded excerpt joins, to distinguish an isolated louder four-second transient from an eligible
search window. Do not infer that every rejection must have its four-second maximum below the gate.
Keep all raw audio and failures; use spares without lowering the gate or inventing silent windows.
For example, `jam_1544396` vocals reach 0.0068258657 over a sliding four seconds, but their loudest
eligible nominal window is only **0.0043206365**: zero eligible audible vocals windows. All nine failed
heroes in the diagnostic have at least one stem with zero eligible windows. Thirty-nine files (three
mixes plus 36 stems) were measured; subsequent failures require a new investigation.

## Checks and execution failures

| Stage | Exact outcome |
| --- | --- |
| Focused reporter | 15 passed / 8.96 s |
| Task 9 ingest | 59 passed / 40.51 s |
| Task 9 worker | 23 passed, 5 skipped / 32.35 s |
| Focused reporter/calibration | 23 passed / 5.53 s |
| Task 10 preliminary ingest / worker | 67 passed / 48.37 s; 23 passed, 5 skipped / 34.16 s |
| Final focused freeze/reporter/calibration | 24 passed / 7.90 s |
| Final ingest | **68 passed / 64.68 s** |
| Final worker | **23 passed, 5 skipped / 51.88 s** |
| Python Ruff check / format-check | Pass, **58 files** |
| Post-feedback focused checks | **25 passed / 7.74 s** |
| Post-feedback final ingest / worker | **69 passed / 48.87 s; 23 passed, 5 skipped / 36.92 s** |
| Post-feedback Python Ruff check / format-check | **Pass, 59 files** |
| make lint | Attempted after each task/final freeze; Make not installed |
| Web pnpm lint / typecheck | Both fail before checking code: no matching pinned @pnpm/exe@12.14.0 |

Five skips are the existing opt-in live worker DB tests; not rerun here. Common helpers are unchanged,
so common tests were not rerun. No global lint, new live worker/API integration or listening pass claimed.

Final test commands: `uv run --project ingest pytest ingest/tests` and `uv run --project worker pytest
worker/tests`, with `-q --tb=short -p no:cacheprovider`, workspace UV cache, cached FFmpeg PATH and
OMP/MKL=2. Fresh basetemps: `ingest/data/pytest-session5-release`, `worker/data/pytest-session5-release`.
Focused final basetemp: `ingest/data/pytest-freeze-final`. Python lint commands are `uv run --project api
ruff check common ingest worker api scripts` and `ruff format --check` on the same paths.
Post-feedback basetemps: `ingest/data/pytest-listening-final`, `ingest/data/pytest-session5-reviewed`,
`worker/data/pytest-session5-reviewed`. No common helper changed during this update.

Initial report network access failed before the DB snapshot; approved rerun worked. Initial calibration
and read-only rejection decode hit protected cache/file permissions; approved reruns worked. Nothing
was repaired by changing ACLs, dependencies, thresholds, vectors or source files. A foreground report
with redirected stderr hit PowerShell 5's native-warning ErrorRecord behavior; the launcher now preserves
the native exit code instead of treating progress/warnings as fatal. The confirmation run produced a
complete clean technical audit with the hero-count gate open. The outer `powershell -Command` tool
reported **host exit 1** (nested nonzero script mapping); the report's documented count-shortfall code
is 2. Do not describe that host result as an all-gates-pass. Detached launcher exits alone are not report
completion evidence. Reporter stdout/stderr and authoritative UTF-8 output JSON are retained.
The final post-feedback command explicitly propagated the child status and **returned exit 2**:
`./ingest/launch-audit.ps1 -Mode report -Output ingest/data/session5/report-reviewed.json -Foreground`
with stdout/stderr redirected to `report-reviewed.stdout.json` / `report-reviewed.stderr.log`, followed
by `exit $LASTEXITCODE` in the automated shell. Its 56-hero shortfall is recorded; technical files pass.

The failed pnpm bootstrap created `.pnpm-store/v11/index.db`; only that new 8 KiB file was removed after
checking its workspace path and creation time. Pre-existing empty cache directories were preserved.

## Processes, logs and next session

Preserve hero uv **32252** / Python **30820**, original start 16:31:16/17 EST. Command:
`uv run --no-sync --project ingest --env-file .env python -m ingest.heroes --mode batch --limit 80`.
Logs: `ingest/data/heroes-batch-20261114-163116.{stdout,stderr}.log`, `ingest/data/heroes/heroes.log`.
Latest separate read-only count snapshot **18:26:11 EST**: **351 tracks (350 library + 1 import),
7,649 windows, 96 stems, 23 hero flags**. These newer two heroes were not part of the final 21-hero
independent full audit. At 18:26:04 the batch log recorded **23/80 completed, nine failures**, next
`jam_1222581` separating; rolling ETA **12,600.887 s (~3 h 30 m)**, projected ~21:56 EST, subject to
later failures/stalls. PIDs 32252/30820 were still alive. Nine rejected heroes were decoded separately.
The original ingest PIDs 29584/7980 remain dead; no restart was needed. No worker daemon was started.

Report launchers 2400 (blocked), 16468 (initial full), 30528 (intermediate full); calibration launchers
33100 (blocked), 30324 (successful), 2484 (freeze-enforced replay), all finished. Logs:
`report-20261114-{175715,175920,180530}.{stdout,stderr}.log` and
`calibrate-20261114-{180445,180827,181645}.{stdout,stderr}.log` under `ingest/data/`.
Final foreground logs: `ingest/data/session5/report-confirmed.{stdout.json,stderr.log}`.
Post-feedback final logs: `ingest/data/session5/report-reviewed.{stdout.json,stderr.log}`.
The earlier redirected failure used `report-confirmation.*`; retain it as failed execution evidence.
Later batch checkpoint 18:32:53 EST: 24/80 completed, ten rejected, next jam_1207327 separating; ETA
12,728.689 s (~3 h 32 m), projected ~22:05 EST. The tenth rejection jam_1342553 occurred after the
final report's failure-log snapshot and nine-hero diagnostic. Only its `heroes.py:164:features` failure
location is known; individual stem RMS is still unmeasured and must be investigated next session.
Ignored read-only diagnostics: `ingest/data/session5/{diagnose_rejections.py,rejections.json,summarize.py}`.
Do not confuse these finished processes with the original continuing hero batch.

Changed files: reporter, calibration runner, audit launcher, expected-error provenance list, two focused
test files, frozen mapping, two committed JSON evidence summaries, this evidence document, ingest README/
PLAN, listening provenance JSON and the explicitly authorized `docs/codex-handoff.md`. No common/worker runtime, schema, API, storage
contract, ID format, dependency, `.env` or model-default edits. Existing schema edit remains excluded;
SHA256 `BB8F20C0BA862279A7B89B12C3E2946AF087E43F10E1AE184132AC2E181F6DF5`.

For Session 6: read the current handoff and plan first; present the assigned eval plan and wait for
approval. Preserve live hero PIDs; only resume after confirming they are dead and target is incomplete.
Refresh the reporter, inspect new failures and record the actual hero shortfall. Collect real listening
judgments for the audition IDs and required 30 timbres. Keep the agreed mapping unchanged. Build the
original 20-query eval dataset/actual `/search` runner, arrange two human graders and retain endpoint/
grading failures honestly. Verify WS2 uses the exact shared CLAP identity and excludes imports; inspect
live API readiness rather than assuming fixture endpoints are real. Never modify API/web files to fix
another stream. Keep hero mix-density completion and the failed semantic fixture gate explicitly open.
