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
