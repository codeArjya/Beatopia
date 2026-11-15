# ingest/ (owner: **WS1**, Audio data & stems)

Library ingest (Freesound, Jamendo, FMA) and the hero stem batch. `vocab.txt` is the tag vocabulary, shared with
`/chips` (WS2) and the chip tray (WS3): announce changes after H12.

```bash
cd ingest && uv sync
uv run --project ingest python -m ingest.run --source freesound --limit 20
```
Plan: `ingest/PLAN.md` (written in the WS1 kickoff). Handoff: `docs/handoff/WS1-data-stems.md`.

Session-2 Windows launch (uses approved general CLAP revision per process; coordinate the same configuration with WS2):

```powershell
./ingest/launch.ps1 -Source freesound -Limit 20 -Foreground
./ingest/launch.ps1 -Source auto -Limit 350
```

The second command starts a hidden background process and prints launcher PID and stdout/stderr paths.
Do not launch a competing ingest: `ingest/data/ingest.lock` is protected by an OS lock, released on crash.
Resume with the same command/data directory after confirming the old process exited. Never delete checkpoints
or change model/revision to bypass the fingerprint guard. Root `.env` and API configuration are unchanged.

`--limit` is a completion target, constrained to 1–400. Discovery allows spare candidates up to a hard queue
ceiling of 400, then stops processing at the completion target. Rejections/errors remain logged and make the
run exit nonzero, even if spare candidates reach the target. An identical resume verifies existing DB rows,
vectors, tags/features and public audio bytes before skipping; failed uploads/DB transactions are retried.
Failed tracks do not abort remaining tracks. `--source jamendo` or `auto` falls back to Freesound when the
Jamendo key is missing; failed/insufficient Jamendo discovery also uses Freesound to fill the bounded queue.
No Freesound credential means a clear discovery failure, not keyless Freesound access.

Artifacts in ignored `ingest/data/`: request response cache, durable API attempt budget/cooldowns,
`fingerprint.json`, `queue.json`, `tracks/{id}/original.audio`, `mix.mp3`, `features.npz`, `manifest.json`,
and append-only `ingest.log`. Manifests record original excerpt offsets and processed playback offsets.
Downloads are sequential, limited to 100 MiB and three attempts; source API attempts are paced at 1.1 s,
capped at 600 per source across resumes (including failed attempts); cooldowns survive restart.
Logs omit credentials/raw provider exceptions and include error type, HTTP status and source location.
ETA is a rolling estimate including startup; early estimates from long Jamendo songs overestimate short
Freesound work. Reruns include verification time and should not be treated as fresh-ingest benchmarks.

Read-only interim verification (with service environment loaded):

```powershell
uv run --project ingest --env-file .env python -m ingest.verify --minimum 20
```

This checks counts, ranges/vector validity and every available manifest against DB/public bytes.
During an active ingest, a manifest may briefly precede its transactional publication; verify again after
that track finishes. This is not the later quality/coverage `report.py`; no listening or hero-quality gate
is implied. Hero/FMA CLI requests fail explicitly until implemented in later sessions.

Source behavior follows the [Jamendo tracks API](https://developer.jamendo.com/v3.0/tracks)
(BY/BY-SA URL validation, `audiodownload_allowed`, `audiodownload`, `ccnc=false`, `ccnd=false`) and
[Freesound API](https://freesound.org/docs/api/overview.html) (licensed HQ previews, no original-download OAuth).
# Hero selection and separation (session 3)

Use `./ingest/launch-heroes.ps1 -Mode audit -Foreground` for a read-only DB ranking/coverage audit;
`-Mode status -Foreground` prints read-only counts even while the batch holds its lock. The launcher
sets the approved immutable CLAP checkpoint, workspace model caches, FFmpeg and two inference threads.
It never changes `.env`. Demucs uses the content-checked legacy `htdemucs` checkpoint, seven-second
segments, split=true, overlap=0.25, one shift and seed zero. CPU is supported; unavailable/failed
accelerators fall back to CPU once. No substitute stem labels/models are published.

```powershell
./ingest/launch-heroes.ps1 -Mode benchmark -Track jam_1030276
./ingest/launch-heroes.ps1 -Mode batch -Limit 1 -Track jam_1121408
./ingest/launch-heroes.ps1 -Mode batch -Limit 80
./ingest/launch-heroes.ps1 -Mode verify -Track jam_1121408 -Foreground
```

Background launches are hidden and return launcher PIDs plus stdout/stderr paths. Do not start a
second hero process while the first is alive. The independent `heroes.lock` preserves concurrent
mix ingest and releases on process death; never delete a live lock. Only after confirming the old
hero process is dead, rerun the same batch command. `python -m ingest.run --hero 80` also dispatches
to the hero pipeline; it requires the same environment as the launcher.

Checkpoints live under ignored `ingest/data/heroes/`: `audit.json`, `queue.json`, `benchmarks.json`,
`status.json`, append-only `heroes.log`, and `{track_id}/separated.json`, four MP3s, `features.npz`,
`manifest.json`. Preserve them. Inference is reusable before embeddings/publication finish;
matching cached files are checked by hash, format, coverage and fingerprint. Incomplete derived
features are repaired; differing model/vocabulary/source fingerprints require an explicit migration.
All uploads and public byte checks precede one DB transaction publishing four stem rows, stem
windows and `is_hero=true`. Reruns verify DB values/vectors and public hashes rather than trusting
the hero flag. `verify` only inspects existing artifacts/DB/storage and never repairs them.

Ranking uses maximum mix-window loopability times distinct selected track tags divided by the
120-entry vocabulary; ties use track ID. Reserve thirty tracks with exact existing horns/keys/strings
tags, then fill by rank. Twenty ranked spares can replace failures without lowering the target.
The queue freezes at batch start; new mix ingest does not reorder it. A failure remains logged and
causes a nonzero final exit even if spares satisfy the count. Audit tags are candidate evidence;
`listening=unreviewed` and `audibly_verified=0` must not be interpreted as human quality approval.

Full stems use the contract paths and processed mix duration, including the recorded excerpt join.
Stem windows never cross the join, drop silence at the unchanged -45 dBFS threshold, and use actual
CLAP embeddings. A candidate lacking audible windows for any of the four stems fails the hero gate.
Stem-window density uses spectral flatness plus the fraction of stems above -30 dBFS. Mix-window
density remains the original onset proxy so concurrent mix verification stays compatible; updating
all hero mix-window densities remains part of the later density-completion task.

Benchmark timings are **local decoded stereo inference**, excluding download, MP3 encoding,
embedding, upload and DB work. They do not establish the on-demand worker's end-to-end <60 s gate.
Batch ETA uses the last ten newly published hero wall times, excluding fast cached verifications;
duration/source changes and future failures can invalidate the projection. See `HERO_SESSION3.md`
and `docs/codex-handoff.md` for measured results and remaining acceptance checks.

## Reporting and calibration (Session 5)

From the repository root, with `.env` loaded and the same pinned CLAP environment as the corpus:

```powershell
./ingest/launch-audit.ps1 -Mode report -Foreground
./ingest/launch-audit.ps1 -Mode calibrate -Output ingest/data/session5/calibration.json -Foreground
```

Without `-Foreground`, launches are hidden and return the launcher PID plus stdout/stderr paths.
The launcher's success only means the process started. Inspect its output JSON and logs for the result.
The underlying report command is `uv run --project ingest --env-file .env python ingest/report.py`;
the launcher supplies the immutable general CLAP revision and cached FFmpeg PATH. `report.py` does not
load CLAP weights, run inference, publish objects or change DB/checkpoints. It takes one repeatable-read,
read-only DB snapshot and closes that connection before checking local artifacts and public audio.
Four bounded HTTP callers hash and fully decode all public library mix/stem objects, then probe the
actual bytes for one stereo 44.1 kHz, 192k MP3 stream. Import rows are counted separately and excluded
from corpus targets. Objects without a local expected hash are explicitly marked `hash_anchored=false`.

The report contains counts for every vocabulary tag, top examples, ten seed-controlled random windows,
missing queued stages, invalid windows, local/DB mismatch checks, public object failures and historical
ingest/hero failures. Queue spares are not missing required library tracks. Seven exact intentional
Session-4 error job IDs are classified using `expected_errors.json`; unfamiliar errors remain unexplained.
No raw DB/provider exception text is printed. Exit 1 means corruption/unexplained job errors or a command
failure; exit 2 means technical count targets remain short. Exit 0, when technical targets are met, still
does not certify listening quality: read `acceptance.full_quality_gate`. PowerShell's outer `-Command`
can map a nested nonzero script exit to host code 1; preserve `$LASTEXITCODE` when automating it.

`calibrate.py` defaults to the initial saved audit `ingest/data/session5/report-task9.json`; pass
`--report <path>` directly to use another audit. It replays zero-shot tagging from cached embeddings,
reports changed selections/scores, and writes a bounded-playback HTML audition beside its JSON output.
It never changes DB rows, manifests, embeddings or audio. A changed selection or score difference
greater than 1e-5 exits 1 for investigation; that tolerance is for replay comparison, not tag selection.
Selected low/high density examples are proxy extremes, not reviewed sparse/dense judgments.

`vocab-freeze.json` records all 120 raw tags and the existing fixture chip IDs, vocabulary/fixture hashes,
prompts, category selection rule and CLAP identity. The human confirmed both WS2 and WS3 agreement in
Session 5. Calibration refuses mapping/model drift before replay. Keep `saxophone` and `bass guitar`
unchanged; do not even edit the vocab header casually because its bytes enter resumability fingerprints.
Future tuning needs actual listening evidence and a coordinated cache/DB migration; bypassing fingerprints
or modifying a live hero's artifacts is not a migration. No such tuning was justified in Session 5.

Recorded evidence: `SESSION5.md`, `REPORT_SESSION5.json`, `CALIBRATION_SESSION5.json`. Full local artifacts
and the audition page remain under ignored `ingest/data/session5/`. Both plan rows remain open for the
unfinished hero-count and listening acceptance; mapping agreement alone does not complete calibration.

## Search evaluation (Session 6)

`eval_queries.yaml` contains twenty listening intents spanning instruments, mood, genre, tempo,
sparse arrangements and isolated stems, including stacked chips and text-only requests. Chip IDs
are checked against the existing contract fixture; no vocabulary or API change is required.
The runner reads the binding Pydantic response models directly, without loading the WS2 app.

From the repository root, once WS2 supplies the actual API URL:

```powershell
uv run --project ingest python ingest/eval.py --base-url https://YOUR-WS2-API --output-dir ingest/data/session7/eval-before
```

It sends all twenty actual `POST /search` requests with `limit=5` and a run UUID. There is no fixture
fallback, automatic retry, direct-DB search substitute or machine-generated relevance grade. Console
and `results.md` show top-five window/track IDs, tags, license, attribution, stem/range, score, plan,
fallback status, HTTP status, latency and failures. `results.json` preserves the request, raw successful
JSON and validated response for each query. Network/provider exception text is not recorded; HTTP
errors retain status and a bounded API error code. Timeout defaults to 30 seconds (`--timeout` overrides).
An output directory must be new, so reruns cannot overwrite a baseline or human reviews.

Known fixture markers, returned private imports, empty results, duplicate windows, ignored limit,
missing license/attribution, nonfinite values and invalid ranges/scores are explicit failures. A lack
of fixture markers does **not** prove live DB search or a matching CLAP model. WS2 must confirm
`laion/larger_clap_general` revision `ada0c23a36c4e8582805bb38fec3905903f18b41` matches the corpus,
imports stay excluded, and the endpoint uses real search. This is a process setting, not a request
to change the shared model default or root `.env`.

The two designated human reviewers are the requesting user and their teammate. Once valid live
results exist, open `audition.html` to hear returned full-track/full-hero windows. It displays credits
and bounds playback using returned start/end times. Browser playback itself still needs verification;
this generated page is not evidence of WS4 playback or range-job offset handling.
Each person independently fills their own `reviewer-A.json` or `reviewer-B.json`: reviewer identity,
ISO timestamp in `recorded_at`, one integer grade per returned result, and listening notes. Rubric:
**0 irrelevant / 1 partial match / 2 useful match** against the query's `listen_for` intent. Grades
start null; technical failures are not turned into relevance zeros. No numerical pass threshold is
invented. Fewer than five returned results remain fewer than five; no rows are fabricated.

```powershell
uv run --project ingest python ingest/eval.py --report ingest/data/session7/eval-before/results.json --grades ingest/data/session7/eval-before/reviewer-A.json ingest/data/session7/eval-before/reviewer-B.json
```

Reviews are tied to the exact run/result digest and ranked window IDs; stale, duplicate, unknown or
noninteger grades and repeated reviewer identities fail validation. Reviewing saved results never
calls `/search`. Investigate actual failures with listening evidence; only change WS1 data/tag code
when justified and compatible with live fingerprints/frozen mapping. Leave WS2/WS4 fixes to owners.
After a justified fix, run the same dataset into a new `eval-after` directory and collect both reviews
again. Compare the saved runs (append these options to the saved-review command for the after run):

```powershell
--before ingest/data/session7/eval-before/results.json --before-grades ingest/data/session7/eval-before/reviewer-A.json ingest/data/session7/eval-before/reviewer-B.json
```

The comparison reports technical failures and per-query mean-grade changes only when both runs have
complete reviews from the same two people; otherwise human deltas stay empty. Exit **1** means
technical/validation failure, **2** means grading/comparison incomplete, **0** means two complete
reviews were supplied. Exit 0 is not an automatic relevance or live-integration acceptance pass.

Session 6 evidence is in `SESSION6.md` and `EVAL_SESSION6.json`. The human confirmed the live API is
not ready; both twenty-query HTTP attempts timed out. No live results, human grades, evidence-backed
relevance fix, before/after relevance improvement or WS2/WS4 integration pass is claimed.
