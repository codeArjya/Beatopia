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
