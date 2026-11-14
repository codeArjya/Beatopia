# worker/ (owner: **WS1**, Audio data & stems)

Polls `jobs` and runs `stems` (Demucs) and `analyze` (import analysis) jobs per CONTRACT §3.
Entrypoint `python -m worker.main` (WS2's container runs exactly this); config comes only from env.

```bash
cd worker && uv sync && cd .. && make dev-worker
```

Run from the repository root so `worker/data` is stable across restarts. Deploy `common/` and
`ingest/vocab.txt` alongside the worker: common analysis reads that vocabulary. Configure FFmpeg,
`DATABASE_URL`, Supabase credentials, `TORCH_HOME`, and matching CLAP model/revision before startup.
The verified corpus uses `laion/larger_clap_general` revision
`ada0c23a36c4e8582805bb38fec3905903f18b41`; the default music checkpoint is incompatible with it.

Windows launcher (uses existing cached tools/models and the corpus CLAP configuration):

```powershell
./worker/launch.ps1 -Mode serve             # hidden process; prints PID and log paths
./worker/launch.ps1 -Mode once -Foreground  # claim/process at most one queued job
./worker/launch.ps1 -Mode acceptance        # live acceptance; only claims jobs it inserts
```

`python -m worker.main` remains the deployment entrypoint. Optional environment settings:
`WORKER_DATA_DIR` (default `worker/data`) and `WORKER_ONCE=1`. Normal polling is once per second
when idle. Only model singletons are cached in process memory.

Claims commit before processing. Each stage commits monotonic progress independently; `done`/1.0
requires completed uploads and DB publication. Errors terminate with null output and a safe message;
`worker.jsonl` records exception type and stack locations without connection strings. A per-track
Postgres session advisory lock serializes duplicate worker jobs without an open transaction. It does
not coordinate with the independent hero batch; frozen hero candidates and full/range object names
remain separate. Do not launch another hero batch or modify its checkpoints.

Stems require finite `0 <= start < end <= duration` and at most 60 seconds, including hand-inserted
jobs. Four-source `htdemucs` and requested six-source `htdemucs_6s` retain their model names and
allowed source names. One CPU retry follows an inference failure; no HPSS or mislabeled substitute.
Six-source real inference is **not verified locally**; its weights must be available on deployment.
The cached engine hashes actual model parameters. Raw separation is checkpointed before publication;
interrupted uploads/DB publication can resume without inference. Full covering stem sets must match
the model and pass public audio format/duration/decode checks before reuse. Partial/corrupt sets are
repaired. Comparisons use Postgres `real` precision to match the existing range column types.

Range files start at local zero: coverage `[5,35]` uses `*_5000_35000.mp3`; requested track time 10
plays at local time **5**. Returned coverage describes the cached file, even for a narrower request.
Contract paths contain no model identifier: a conflicting model or distinct sub-ms range mapping to
the same filename fails explicitly, preserving the previously published object. Coordinate a contract
change if simultaneous model variants for the same range are needed. On-demand jobs publish stem
rows, not overlapping search windows; mix/import and full-hero windows keep their deterministic IDs.

Analyze jobs require an existing import placeholder and `imports/{id}/original.{ext}`. They retain
the full uploaded timeline, normalize to 44.1 kHz stereo MP3 192k at `imports/{id}/mix.mp3`, index
audible mix windows with real CLAP embeddings/tags, and preserve supplied title/artist/license/
attribution. Imports remain `source='import'` and must be excluded by WS2's public search. No license
is invented. Checkpoints include original hash, model/revision and vocab; identity changes require
explicit migration. Public-byte verification precedes atomic track/window publication.

Recovery: preserve the entire data directory and logs. A process crash can leave `running`; no timeout
automatically reclaims it. Confirm the owning process is dead first, investigate its job ID and logged
failure location, then explicitly requeue only that ID (`status='queued', progress=0, output=NULL,
error=NULL, updated_at=now()`). Do not bulk-reset running jobs or delete checkpoints/locks. DB outage
during terminal publication can also leave a running row; an explicit retry reuses completed stages.

Checks from repo root (set FFmpeg PATH and a fresh workspace pytest basetemp on Windows):

```bash
uv run --project worker pytest worker/tests -q --tb=short
# Opt-in: inserts labeled invalid jobs and retains terminal audit rows.
WORKER_LIVE_TESTS=1 uv run --project worker --env-file .env pytest worker/tests/test_jobs_live.py -q -s --tb=short
```

Use `--tb=short` for live tests: dependency tracebacks with locals can expose connection configuration.
See `SESSION4.md` for actual acceptance evidence and limitations. The current API routes still return
fixtures, so direct worker acceptance does not establish live API/browser integration.
