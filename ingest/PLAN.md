# WS1 Audio data & stems plan

Status: approved by the human; implementation started on `ws1-data`. Commit after each task.
Read fully: `AGENTS.md`, `docs/CONTRACT.md`, `docs/handoff/WS1-data-stems.md`.
Only edit `common/`, `ingest/`, `worker/`, `db/migrations/`. No shared-file changes or dependency swaps are authorized by this plan.

## Decisions (handoff §5, all 16 items)

1. **Sources and counts.** Target 350 tracks: approximately 200 Freesound and 150 Jamendo, within the 300–500 goal. Freesound uses vocab queries, `filter=license:("Creative Commons 0" OR "Attribution") duration:[4 TO 60]`, token authentication, and `previews.preview-hq-mp3`. Request metadata including id, name, username, license, duration, tags, URL and previews in search results to avoid per-track lookups. Validate returned license URLs against CC0/BY; never infer eligibility from tags. Jamendo is conditional on `JAMENDO_CLIENT_ID`: `/v3.0/tracks/`, `client_id`, `format=json`, `include=licenses+musicinfo`, `audioformat=mp32`, pagination; inspect `license_ccurl` for BY/BY-SA only and require `audiodownload_allowed` with a nonempty download URL. Preserve exact license version, source URL, artist, and attribution including excerpt/transcoding notice. If unavailable, expand Freesound toward 350. FMA is omitted from the critical path: no verified small downloadable subset yet; only revisit if one can be verified within a one-hour cap. Skip ccMixter/Archive. [S1–S3]

2. **API budget.** Retain 60 requests/minute, 2,000/day and at most 600 WS1 Freesound API requests total, including retries; pace below the ceiling and reserve room for WS2 fallback. Cache every JSON response by normalized request parameters without credentials, deduplicate IDs, checkpoint pages, back off on 429 and honor Retry-After when supplied. Count preview downloads separately and bound concurrency; do not assume CDN traffic is covered by the API allowance. [S1]

3. **Long-song excerpts.** Retain first 120 seconds plus one 60-second middle excerpt, storing only this processed mix, at most 180 seconds. For duration D > 180, middle start is `min(D-60, max(120, D/2-30))` to avoid duplication; for D <= 180 retain the whole clip once. Concatenate on a new processed timeline, record source offsets locally, and never generate windows spanning the artificial join at 120 seconds. Analyze pieces separately, offset their beats to processed time, and derive track tempo/key from their evidence. All DB durations/ranges refer to the stored mix, including full-length hero stems. This qualifies the full-clip beat-tracking default to avoid false beats at the splice. [S8]

4. **Windows.** Retain nominal 10-second length and 5-second hop; drop linear RMS below `10**(-45/20)` (~0.00562); store linear RMS. Concrete clarification: allow one truncated terminal window of at least 4 seconds and stop after it. Thus 16 seconds yields `[0,10]`, `[5,15]`, `[10,16]`, satisfying the handoff's three-window check; 4–9 second one-shots remain searchable. Zero-pad only model inputs, never stored ranges. Apply independently to each excerpt/stem. No zero-length or mostly silent padded windows.

5. **BPM and beats.** Use `librosa.beat.beat_track(y=..., sr=..., units="time")` over each complete processed excerpt. The API returns tempo and beats, not confidence; convert its tempo array safely to a scalar. Retain beats in seconds; set BPM null for fewer than eight usable beats, nonfinite tempo, or interbeat-interval coefficient of variation > 0.20. These are initial application heuristics to evaluate, not a librosa confidence API. Silent input has null BPM and empty beats. [S4]

6. **Key.** Retain CQT chroma plus Krumhansl–Schmuckler major/minor template correlation across 12 rotations, deterministic tie-breaking and canonical spellings such as `A minor`/`F# major`. Null for silence, too-short chroma input, or degenerate correlations. No external key-detection library. [S4]

7. **Loopability.** Retain mean cosine similarity of consecutive four-beat bar onset envelopes, resampled to equal length, clipped to [0,1]. Assume 4/4 (no time-signature field); with fewer than two complete bars or unreliable beats use conservative zero, never invent a measured score.

8. **Density.** Retain spectral flatness plus fraction of active stems above -30 dBFS for completed heroes; nonheroes use flatness plus onset rate. Initial bounded formula: equal-weight mean of flatness and active-stem fraction, or flatness and `min(onsets_per_second/10,1)` without stems. Recompute hero windows after separation. This is a sparsity proxy, not a calibrated instrument count; inspect sparse/dense examples before H12.

9. **CLAP.** Retain `laion/larger_clap_music`, `ClapModel`/`ClapProcessor`, 48 kHz, float32 L2-normalized 512 dimensions, lazy model singleton, inference mode, batch 16. Only `common/clap.py` resamples for CLAP. Downshift batch on OOM before changing device; never change model to solve performance. Pin/log a common model revision for ingest and WS2. Model config confirms projection 512; preprocessing config confirms 48 kHz. Current Transformers docs describe structured feature outputs, so do not assume older examples return a bare tensor: extract projected features and assert `(n,512)` against the installed version before ingest. Cache vocab text embeddings and handle empty batches. [S5]

10. **Zero-shot tags.** Retain `a recording of {tag}` prompts and cosine similarity; independently per category retain top three scores strictly above category mean + one population standard deviation. Store every vocab similarity under the same raw tag strings in `tag_scores`. No threshold relaxation hidden inside ingest; quality tuning before H12 is explicit and re-tags cached embeddings.

11. **Vocab.** Retain the existing roughly 120 entries (60 instruments/30 genres/30 moods), category headers, raw strings and requested instrument coverage. WS2 owns chip ID mapping from these strings. Freeze by H12; coordinate any later change with WS2/WS3. Do not silently rename `saxophone` or `bass guitar` to handoff shorthand.

12. **Heroes.** Retain target 80, rank by loopability times normalized distinct-tag diversity, deterministic ties by track ID. Reserve at least 30 qualifying horns/keys/strings tracks; curate more source queries if the pool lacks coverage. Require audibly useful candidates, not just high numerical scores. Mark hero complete only after storage, stem rows and embeddings exist; log shortfalls instead of claiming quotas achieved.

13. **Stem model.** Retain maintained Demucs 4.1 `htdemucs` for four stems; `htdemucs_6s` only by request (adds guitar/piano; upstream warns about piano quality). Device preference CUDA, then available MPS, then CPU; retry CPU on MPS error. Explicit model/device selection via the documented Separator API; bounded segments, split enabled, overlap 0.25 and one shift initially. Separate no more than 180 seconds at once. Benchmark installed build before overnight work. [S6]

14. **Stem storage.** Retain 44.1 kHz stereo MP3 192k at contract full-length/range paths, embed `other`, `bass`, `drums`, `vocals` windows; optional six-source outputs use allowed guitar/piano names. Range files begin at local time zero while metadata retains absolute track coverage. WS2/WS4 must translate playback offsets. Never claim an excerpt is full original-song audio. [S8]

15. **Worker.** Retain one process, one-second polling, short transaction with `FOR UPDATE SKIP LOCKED` and status transition to running, then commit before inference. Validate finite `0 <= start < end <= duration` and range <= 60 seconds, update monotonic stage progress/updated_at, mark done only after uploads/DB output succeed, and serialize contract `Stem`/`TrackDetail` output shapes. Analyze imports through the same normalization/features/embedding pipeline, updating WS2's placeholder without losing metadata. On failure retry Demucs on CPU once. **Exception:** python-audio-separator is absent from manifests and adds another inference/model stack; defer it pending dependency review. HPSS only separates harmonic/percussive audio, which are not contract StemName values and cannot honestly represent vocals/bass. Until owners agree on fallback semantics, return a clear job error rather than mislabeled success; HPSS may be inspected locally but not published as requested instrument stems. Do not invent a package version or fallback mapping. A crash leaves a running job: after confirming the previous worker is dead, recover/requeue explicitly; no unsafe automatic timeout while a job may still run. [S6,S9,S10]

16. **Idempotency.** Retain resumable stages, but row existence alone is insufficient after interruption. Check expected object paths, window IDs/counts and complete stem coverage before skipping; use deterministic IDs, storage upsert and DB conflict handling. Publish rows transactionally per stage after successful uploads; repair partial work on rerun. Keep per-stage input/model/vocab fingerprints locally and refuse silently mixing model revisions; identical reruns change neither counts nor results. [S7]

## Verified dependencies and evidence

Read repo manifests, lockfiles and helper stubs on 2026-11-14. No `.venv` exists under common/ingest/worker; `uv`/`python` were not resolved by PowerShell Get-Command. These are **locked**, not verified installed versions: librosa 0.11.0; transformers 5.23.0; psycopg 3.3.9; pgvector 0.5.1; supabase/storage3 2.34.1; ingest/worker demucs 4.1.0. Windows/Linux locks select torch 2.15.0+cpu; other platform branches differ (common 2.15.0 vs ingest/worker 2.2.2). Do not assume CUDA or cross-platform compatibility. First implementation task must sync/inspect actual imports and record versions/devices; no runtime or speed result is claimed here. No dependencies installed for this planning task.

Upstream documentation read for API details (docs can differ from future lock versions; installed smoke checks remain mandatory):

- **S1:** [Freesound overview](https://freesound.org/docs/api/overview.html) and [resources](https://freesound.org/docs/api/resources_apiv2.html): rate limits, preview access, search filters/fields. HQ MP3 preview is approximately 128 kbps; transcoding to contract 192k does not improve source quality.
- **S2:** [Freesound authentication](https://freesound.org/docs/api/authentication.html): preview access without original-download OAuth flow.
- **S3:** [Jamendo tracks](https://developer.jamendo.com/v3.0/tracks): parameters, license URL and download permission fields.
- **S4:** librosa 0.11 [beat_track](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html) and [chroma_cqt](https://librosa.org/doc/0.11.0/generated/librosa.feature.chroma_cqt.html): keyword-only calls, tempo/beat outputs, chroma input.
- **S5:** [model config](https://huggingface.co/laion/larger_clap_music/blob/main/config.json), [preprocessing config](https://huggingface.co/laion/larger_clap_music/blob/main/preprocessor_config.json), [Transformers CLAP API](https://huggingface.co/docs/transformers/model_doc/clap): processor/model and projected feature interfaces.
- **S6:** [maintained Demucs](https://github.com/adefossez/demucs) and [Separator source](https://github.com/adefossez/demucs/blob/main/demucs/api.py): model names, explicit device, split/segment/overlap/shifts and callback support. Verify callback behavior locally before using it for progress.
- **S7:** [Supabase Python upload](https://supabase.com/docs/reference/python/storage-from-upload): `storage.from_(...).upload(file=..., path=..., file_options=...)`; set `content-type` to `audio/mpeg`, `upsert` to string `true`. [pgvector Python](https://github.com/pgvector/pgvector-python): `pgvector.psycopg.register_vector(conn)` on every connection, after extension creation; parameterized vector writes.
- **S8:** [FFmpeg](https://ffmpeg.org/ffmpeg.html): explicit output sample rate/channels/bitrate (`-ar 44100 -ac 2 -b:a 192k`); check local encoder availability.
- **S9:** [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator): separate package/model/runtime requirements; not an installed bootstrap dependency.
- **S10:** [librosa HPSS](https://librosa.org/doc/0.11.0/generated/librosa.effects.hpss.html): harmonic and percussive outputs, not instrument separation.

## Needs from other streams

| Need / owner | Assumption meanwhile |
| --- | --- |
| Human: Python 3.11/uv/FFmpeg, service credentials, public audio bucket and initialized DB; GPU availability | Use synthetic fixtures and mocked services for local checks; no claim of real-data gates until credentials/runtime work. Never print secrets. |
| WS2: identical common CLAP code/model revision, packaging of vocab, shared Freesound quota reservation | Default contract model; deploy matching common plus ingest/vocab.txt; cached fixture responses until seed exists. |
| WS2: import placeholder metadata (license/attribution), job insertion and canonical TrackDetail serialization | Preserve supplied placeholder fields; require valid metadata, never invent a CC license for user uploads. Test against shared fixtures and model shapes. |
| WS2/WS4: processed-excerpt timeline and range-stem local playback offsets | Contract ranges mean absolute processed-track coverage; range audio seek is requested time minus range_start_s. Publish examples in ingest documentation. |
| WS2 deploy: worker container/device budget, model cache, environment and health/restart handling | `python -m worker.main`, env-only settings, CPU-supported deployment; <60 seconds remains a benchmark target, not a promise. |
| WS2/WS3: vocab/chip mapping and freeze; two humans for query grading | Existing raw vocab strings; freeze H12; save eval output even if endpoint/graders unavailable. |

## Contract changes

No schema/signature change is required for the primary implementation. Continue with CONTRACT unchanged.

1. Fallback stem semantics need owner agreement: harmonic/percussive outputs cannot be represented faithfully by the existing enum. Meanwhile jobs fail clearly after Demucs retries; no new stem names or fake four-stem output. python-audio-separator requires separate dependency review.
2. Clarify processed-excerpt timeline, short terminal windows and range-file playback origin with WS2/WS4. Meanwhile use the exact decisions above; all offsets refer to stored mix, and range coverage is explicit metadata. No added public fields.
3. Durable job leases/model-version fields could improve recovery but are unnecessary for the single-worker MVP. Meanwhile recover crashed running jobs manually and keep local fingerprints; do not alter jobs schema.

If an owner requires a contract amendment, stop before editing outside WS1 and ask the human to land a coordinated `contract:` PR. Proposed wording/diffs can first live in ingest documentation; this task's explicit path restriction prevents writing `docs/proposals/` directly.

## Tasks and gates

Each checkbox is a 1–2 hour active work unit; unattended downloads/inference add wall time. H values are hackathon elapsed targets, not guaranteed estimates. The handoff compresses foundation work into three hours: treat H3 as a tight critical path and report slippage early rather than weakening checks. No implementation starts before plan review.

| Done | Gate / effort | Refined task (handoff task) | Acceptance check |
| --- | --- | --- | --- |
| [x] | H3 / 1 h | Runtime preflight + common I/O/DB/storage/IDs (#1) | Completed: see execution record below. Record actual versions, ffmpeg encode/decode and available device; pgvector roundtrip; upload twice to same path, public playback 44.1 kHz stereo; existing common tests pass. Start model downloads early. |
| [ ] | H3 / 1 h | Shared lazy CLAP + initial analysis/tagging (#1–2) | Implementation and offline tests complete; default checkpoint fails semantic acceptance. See `CLAP_MODEL_REVIEW.md` and execution record. Fixture and drum-loop text finite normalized `(1,512)`, cosine >0.2; 90 BPM ±2, three bounded windows from 16 s; silence/short input safe; vocab scores complete. Failure is investigated, never patched with a magic score. |
| [x] | H3 / 1 h | Freesound source + minimal resumable seed pipeline (#3) | `uv run --project ingest python -m ingest.run --source freesound --limit 20`: 20 real licensed tracks with playable storage, nonempty searchable windows and normalized embeddings; repeat adds no duplicates; notify human seed is ready for WS2. |
| [x] | H8 / 1 h | Harden analysis/ingest recovery (#2–3) | Tests cover join boundary, low-confidence BPM, terminal windows, corrupt download, partial upload/DB failure and resume; no invalid ranges/vectors or missing attribution. |
| [x] | H8 / 1 h | Jamendo adapter and full run kickoff (#4) | BY/BY-SA and download-permission filtering checked; long excerpt duration/offsets agree with playback; absent key switches to Freesound; queue target ~350 (CLI limit 400 ceiling), bounded requests and ETA logged. FMA stays excluded unless small subset verified. |
| [ ] | H8 / 2 h | Hero selection and resumable batch (#5) | Candidate ranking/30-track coverage audit, 30 s and 180 s benchmark, one complete hero with four playable stems and windows; start 80-track batch, record ETA and failures. H8 checkpoint reports actual mix/hero counts and projected H12 finish; no false completion if batch runs longer. |
| [ ] | H12 / 1 h | Worker claiming/status/progress + stem jobs (#6) | Competing DB claim test selects a job once; valid range succeeds with contract output; invalid/>60 s rejected; failure terminates as error; no long-held claim transaction; progress visible to separate connection. |
| [ ] | H12 / 1 h | Worker import analysis + range caching (#6) | Hand-insert analyze job on valid original -> updated placeholder, playable normalized mix, windows, TrackDetail output; malformed input errors; stem range paths/absolute metadata/local offsets agree; reuse covering stems; time end-to-end 30 s job on CPU and available GPU, report whether <60 s. |
| [ ] | H12 / 1 h | Reporting + coverage/quality audit (#7) | report prints counts by source/tag/license, top-tag examples, ten random windows, missing objects/stages and errors; 300–500 playable licensed tracks and 80 complete heroes (or explicitly reported cut), at least 30 required hero timbres; inspect random audio and run stream checks. Notify human full-library status. |
| [ ] | H12 / 1 h | Tag calibration and vocab freeze (#7) | Sparse/dense and horns/keys/strings examples inspected; tune thresholds/prompts only with evidence, re-tag affected windows from cached embeddings; publish tag examples and freeze mapping with WS2/WS3. |
| [ ] | H20 (H12–H14) / 2 h | Twenty-query eval dataset and runner (#8) | `ingest/eval_queries.yaml` covers instruments, mood/genre, tempo, sparse/stem cases; runner calls actual `/search`, prints top five with IDs/tags/license and handles errors; two humans grade relevance and record failures. |
| [ ] | H20 (H14–H16) / 2 h | Address eval failures and integration (#8) | Re-run failed queries after targeted data/tag fixes; record before/after human grades, no invented pass threshold; validate actual job polling/playback with WS2/WS4 or retain explicit unresolved dependency. |
| [ ] | H20 (after H16) / 2 h | Optional two-model quality comparison (#9) | Only if core gates passed: on a small held-out set report cross-correlation, residual energy and CLAP label similarity plus listening; use supported models, log actual model chosen; do not double all jobs without latency evidence. |
| [ ] | H20 (after H16) / 1 h | Complete hero density + final handoff (#9) | All completed hero windows have stem-activity density; repeated report/checks clean; final counts, failed jobs, 30 s timings, eval grades, recovery commands and any cuts documented. Density completion remains required even if optional quality comparison is cut. |

After every implementation task: run relevant focused tests, `make lint`, `uv run --project ingest pytest`, `uv run --project worker pytest`, and `uv run --project ingest python ingest/report.py` once the reporter exists; include common tests for shared-helper changes. Mark a checkbox only with recorded acceptance evidence. Until report.py exists, report counts with read-only DB checks. If global lint fails outside ownership, record it and notify owner, do not edit their files. This documentation-only kickoff is verified by diff/path review; runtime checks are deliberately not represented as passed.

## Risks and slow-first-run response

- **Setup and weights dominate early elapsed time.** No verified local runtime or model cache. Preflight before promising H3; start downloads before feature work, record cold/warm timings and compatibility failures. Keep source credentials out of logs/caches.
- **First ingest too slow:** instrument first 5 tracks (fetch, decode, features, embedding, upload, DB) and project ETA from the 20-track seed, separately for mix and heroes. If seed threatens H3 or library threatens H12, report stage timing/counts immediately. Cache downloads/JSON/text embeddings, reuse model singleton, batch embeddings, avoid per-window DB roundtrips, and use modest bounded I/O concurrency. Benchmark before increasing CPU concurrency or GPU batches. Do not skip licensing, silence checks or embedding normalization for speed.
- **Cut order:** drop FMA, then Jamendo if its integration/downloads dominate (replace with short Freesound tracks), then heroes 80 -> 40, then omit drums/vocals embeddings while retaining other (and bass if affordable), then optional Tier 2 comparison. Do not start optional Tier 2 while core gates are at risk. Continue queued work from checkpoints; report reduced hero gates honestly. Mix-library target remains 300–500; if infeasible report actual count/ETA for review.
- **CPU-only separation may miss <60 s.** Benchmark a real 30 s job including download/upload; model warm-up separately. Request available GPU deployment through human/WS2, prewarm model, prioritize ready hero stems for demo. Preserve requested model fidelity; do not hide slower performance behind fake progress or degraded stems.
- **OOM/overnight interruption/Wi-Fi.** Bound separation to <=180 s and embedding batches; checkpoints survive interruption; model weights cached; exponential backoff with finite retries; per-track failures do not abort the library. Keep laptop awake via human setup; record batch completion/error summary.
- **Synthetic feature tests can mislead.** 90 BPM fixture tempo may be perceived at half/double time; inspect onsets if the exact ±2 check fails. Key, density, loopability and tag scores need listening checks and diverse eval queries, not just unit assertions.
- **Public import storage and ambiguous licensing.** Preserve WS2-supplied import metadata; public bucket is contract behavior, no secret material in object names/metadata. Coordinate any privacy change through contract owners.
- **Storage/DB divergence and stale fingerprints.** Upload before transactional publish; resume validates all stages, preserve source provenance; changed model requires re-embedding with the same revision for query and corpus. No automatic incompatible model swap.

## Execution record

### Task 1 — common I/O, database, storage and IDs

- Implemented local/HTTP(S) decoding to finite float32 mono with explicit channel averaging; atomic 44.1 kHz stereo 192k MP3 encoding; pgvector registration with clean transaction state and cleanup on registration failure; storage upsert with explicit content type and closed file/storage clients; rejection of nonfinite window times.
- Added `python -m common.preflight [--live]` and documented Windows FFmpeg PATH setup in `common/README.md`.
- Installed frozen common/ingest/worker environments. Actual runtime: Python 3.11.18; NumPy 2.4.6; librosa 0.11.0; Torch 2.15.0+cpu (CUDA false, MPS false); Transformers 5.23.0; psycopg 3.3.9; pgvector 0.5.1; Supabase/storage3 2.34.1; ingest/worker Demucs 4.1.0. No manifests or locks changed.
- Downloaded FFmpeg 9.0.2 Windows essentials from the provider linked by ffmpeg.org, verified its published SHA256 and unpacked under ignored `common/data/tools/`. CLAP cache download initiated under ignored `common/data/huggingface` for task 2.
- Tests: common 26 passed, ingest 1 passed, worker 1 passed (executed with their own environment interpreters). Python Ruff lint and format checks passed across common/ingest/worker/api/scripts. `git diff --check` passed for WS1 edits.
- Live acceptance: 512-dimensional NumPy insertion/pgvector retrieval passed; database extension is 0.8.2; table counts tracks=0, windows=0, stems=0. Storage upload twice, public byte/content-type match and audio decode passed; synthetic test object removed. MP3 output verified 44.1 kHz and two channels. No library rows or migrations written.
- Installed pgvector 0.5.1 returns `Vector`, not an ndarray; the roundtrip check now uses `.to_numpy()`. Audio tests caught FFmpeg's default stereo-to-mono gain, fixed by preserving channels during decoding and averaging explicitly.
- Check limitation: `make lint` could not start because Make is not installed. Its Python checks were run directly and passed; global web checks were not run for this Python-only task. `ingest/report.py` does not exist yet, so preflight's read-only counts provide the planned interim report.
- Pre-existing modification in `shared/schema/api.schema.json` is outside WS1 and excluded from this task's commit.

Task 1 commit: `01ea00b` (`feat(ws1): implement shared audio and service helpers`).

### Task 2 — implemented, semantic acceptance blocked on checkpoint choice

- Implemented lazy shared CLAP, pinned default revision, serialized model initialization/inference, batch 16 with OOM downshift, finite normalized 512-dimensional outputs, deterministic long-input cropping and exact-duration 48 kHz resampling. Installed Transformers source confirms projected features are `.pooler_output` in this version.
- Implemented full-clip beats/BPM confidence, chroma-template key, bounded windows including terminal excerpts, silence removal, onset-bar loopability, spectral/onset density and per-category top-three zero-shot tags with all 120 scores.
- Offline checks: common **45 passed**, ingest **1 passed**, worker **1 passed**. Python lint/format checks pass. Make remains unavailable; global web lint is not claimed. No library ingest or report.py yet; task 1's DB counts remain the last live count check (zero corpus rows).
- Mixed fixture: 90.666 BPM, A minor, windows [0,10], [5,15], [10,16]. Real unit-length output shapes pass. But contract-default `larger_clap_music` scores only 0.002979 against `drum loop`; unrelated text embeddings have mean cosine 0.999295. Direct model forward reproduces this. The dedicated drum fixture also fails (0.011423).
- Investigated against publisher discussion and a matching independent reproduction. Tested `larger_clap_general` using per-command environment overrides only: unrelated-text mean cosine 0.293701; dedicated drum fixture cosine 0.277668, all semantic smoke checks pass. Mixed fixture cosine 0.186066 still misses 0.2 and is recorded as a failure, not hidden. Both checkpoint revisions and exact reproduction commands are in `CLAP_MODEL_REVIEW.md`.
- The proposed configuration is concrete and tested. Root `.env` and WS2 settings are outside WS1 ownership; coordinate the same model/revision in all processes before real ingest. Checked-in contract default, shared files and project environment were not changed. Task 2 stays unchecked pending that decision; implementation and diagnostics are committed as a reviewable checkpoint.

Superseded by session 2 below: seed ingest is verified and the full run is active. Mixed-fixture semantic
acceptance and WS2's matching model configuration remain open.

### Session 2 — recovery, sources and full-library kickoff (2026-11-14)

Human approved the reviewed plan, including the missing Freesound prerequisite, per-process general CLAP
revision and the `docs/codex-handoff.md` exception. No shared default, `.env`, schema, public signature, ID or
storage contract changed. Original scope explicitly covers recovery/Jamendo/full-run kickoff; hero separation
remains for the next session, despite differing original/refined task numbering.

- Added `ingest/sources.py`, `pipeline.py`, CLI implementation, hidden Windows launcher, read-only interim
  `verify.py`, and 24 additional ingest tests (25 including smoke). Added nine analysis cases and fixed empty
  tempo arrays plus finite/sorted/deduplicated beats. DB/storage helpers' public signatures are unchanged.
- Recovery evidence: tests exercise invalid licenses/download permissions, corrupt downloads, excerpt joins,
  terminal boundaries, uncertain BPM, partial upload/DB failure, resume, missing DB vectors/tags/objects,
  normalized vectors, missing attribution, API cache/budgets/durable cooldown, key fallback and CLI ceiling.
  Long-audio test uses actual stereo FFmpeg encode/decode (400 s original -> 180 s processed), with mocked
  CLAP solely for that offline test. Real ingest uses the actual pinned model, never synthetic embeddings.
- Initial DB counts verified zero. Seed PID 26284: 20 real CC-BY-4.0 Freesound tracks and 20 windows in 110.875 s;
  first successful track 33.829 s including model load, warm short tracks ~3.6–4.7 s. One quiet source rejected:
  fs_507355 duration 6.48535 s, RMS 0.0049312245 < 10**(-45/20). Threshold unchanged. Exit 1 retains this failure.
- Repeat PID 14356: all 20 outcomes `verified_existing`, 16.828 s; count remains 20/20/0. `ingest.verify
  --minimum 20` exit 0: all 20 public MP3 hashes and DB vectors/tags/features match; invalid windows=0,
  failures=[], no jobs. Seed is available to WS2 once its model/revision matches the ingest launcher.
- Full run launched 14:52:43 EST: uv PID 29584, Python PID 7980, target 350, queue ceiling 400. Queue sources:
  Jamendo 150, Freesound 250. Licenses: BY-SA-3.0 116, BY-3.0 64, CC0 95, BY-4.0 125.
- Live Jamendo example jam_1030276: public bytes/DB verified true; duration=180.0, 34 windows; source ranges
  [0,120] and [122.2208843537415,182.2208843537415] map to processed [0,120] and [120,180]. No crossing join.
  First two Jamendo tracks 52.453 s cold / 23.640 s warm. At 14:54 EST read-only counts: 22 tracks, 88 windows,
  0 stems. Rolling ETA after two tracks=14621.394 s (~4.06 h), heavily startup/source-biased; not a guarantee.
  Request budget then Freesound=8 (includes sandbox failures), Jamendo=4; bounded below 600/source.
- Final tests: ingest 25 passed (21.22 s), common 54 passed (22.70 s), worker 1 passed (0.01 s).
  Final rerun after derived-cache corruption coverage: ingest 25 passed in 23.20 s, worker 1 passed in 0.02 s.
  Python Ruff check/format over common/ingest/worker/api/scripts passed (40 files). `git diff --check` passed.
  `make lint` attempted three times, unavailable (Make missing). Both `pnpm lint` and `pnpm typecheck` fail before
  checking code because pinned @pnpm/exe@12.14.0 cannot be fetched; web dependencies are absent. No web repairs.
  Initial escalated combined test attempt: 55 passed/19 setup errors due pytest temp-directory ACLs; fixed run
  configuration using fresh workspace temp directories, then combined suite passed 74/74 before final additions.
  Initial uv cache lock denial fixed by workspace UV_CACHE_DIR. No tests/criteria were weakened.
- `ingest/report.py` is not implemented; read-only SQL/verify used as required. Full library completion, hero
  count, listening quality, 30-instrument hero coverage and the mixed-fixture CLAP >0.2 gate are NOT verified.
  Full PID/log status and exact next steps are in `docs/codex-handoff.md`. Leave running work/checkpoints intact.
  Final DB snapshot approximately 14:58 EST: 36 tracks / 463 windows / 0 stems, adapter roundtrip passed.
  Last observed full-run progress before this snapshot: 14 completions, 0 failures, ETA 7505.256 s (~2.08 h).
