# Session 6: search eval tooling and explicit live dependencies

2026-11-14. Plan approved before implementation. Started `5feb19b` on `ws1-data`.
Scope: original refined tasks **11–12**. Tooling is implemented; **both acceptance checkboxes remain
open**. The human confirmed the live API is not ready and designated the requesting user and their
teammate as the two relevance reviewers. No human grades exist yet.

## Implemented and verified

- `eval_queries.yaml`: exactly 20 unique queries; instrument/mood/genre/tempo/sparse/stem coverage,
  stacked existing chip IDs and text-only cases, with explicit listening intents. No desired IDs/grades.
- `eval.py`: actual HTTP `POST /search`, `limit=5`, unique run/session UUID, bounded timeout, preserved
  requests/responses, console/Markdown top-five IDs/tags/licenses/credits/stems/ranges/plans/errors.
  Reads binding Pydantic models without importing the WS2 app or adding dependencies.
- Each new output directory contains `results.json`, `results.md`, `audition.html`, and two independent
  ungraded reviewer JSON files. Existing runs cannot be overwritten. Reviewer identity/timestamp,
  exact run/result hash, ranked window identity and integer 0/1/2 grades are validated. No automatic
  relevance score or pass threshold. Saved-review commands do not repoll the service.
- Fixture markers, returned private imports, ignored limits, duplicate windows, empty results,
  missing credits, invalid ranges/scores and nonfinite responses are explicit technical failures.
  Errors never silently trigger fixtures. NaN/Infinity become serializable error evidence. Tests
  cover HTTP/timeout/network/redirect/schema failures, snapshot mismatches and partial comparisons.
- Generated audition HTML bounds playback for full-track/full-hero search URLs and displays credits.
  **Actual browser playback is unverified**, as is range-job playback. No WS4 pass is inferred.

## Actual HTTP attempts and two-human grading

| Attempt | Started (EST) | Run UUID | Result |
| --- | --- | --- | --- |
| Initial | 18:51:25 | 3ccf0d1c-e987-4763-9242-e506d674b2d3 | 20 requests, 20 timeouts, exit 1 |
| Unrestricted network confirmation | 18:52:54 | c323334d-a4c6-4b49-af15-f77a5460f8dd | 20 requests, 20 timeouts, exit 1 |

Both target `http://127.0.0.1:8000/search` with a two-second timeout. No local port-8000 listener
was listed by `netstat -ano -p tcp`; `/health` was also unavailable. The human separately confirmed
the live API is not ready. **Zero returned results and zero human grades**; technical errors are
not assigned relevance zeros. Grade templates contain no fabricated result rows.

Artifacts: `ingest/data/session6/{eval-before,eval-network-confirmed}/` and sibling
`eval-{before,network-confirmed}.{stdout,stderr}.log`. Exact run/dataset/result/artifact hashes and all
40 query failures are committed in `EVAL_SESSION6.json`. Initial/confirmed result file hashes:
`3c813906c4f92f01c6235eb695aa972e72668156211172dd06bd1f633162a82c` /
`74aa9640315d4b461454e1ca8b2ee0dc81de8f45d3d045068d3ae60aa0d557ab`.

The saved comparison reports 20 → 20 technical failures, `human_comparison_available=false`, and
empty grade deltas. This is an access-confirmation retry, **not a post-relevance-fix run**. No real
results justify changing data/tags or frozen fingerprints; no relevance fix or improvement is claimed.
The README gives exact commands for live runs, both reviewers and before/after comparisons.

## WS2/WS4 dependencies

- `api/app/main.py:90`: search returns the fixture unconditionally, even if USE_FIXTURES is disabled.
  WS2 must supply a real endpoint, identify the deployed revision and confirm matching general CLAP
  model/revision: `laion/larger_clap_general` / `ada0c23a36c4e8582805bb38fec3905903f18b41`.
  WS2 must verify live DB search excludes `source=import`. The runner cannot attest deployed weights.
- `api/app/main.py:100,109`: stems/jobs return fixture outputs; `web/lib/api/client.ts:80` simulates
  running→done polls. Existing Session-4 DB acceptance is not HTTP/browser integration evidence.
- WS2/WS4 must demonstrate a real queued request, GET `/jobs/{id}` every 1 s, visible progress and
  terminal output, then actual browser playback. `web/app/editor/editor-placeholder.tsx:34` currently
  renders whole-track audio. Range-stem seek is **requested_start_s − Stem.range_start_s**; e.g.
  coverage [5,35], requested [10,20] means local [5,15]. Keep absolute metadata and local file origin.
- Once live results exist, user and teammate listen independently and fill their review files.
  Re-run after justified WS1 fixes and record both sets of grades. API/web fixes stay with owners.
  No external messages were sent and no API/web/shared files were edited in this session.

## Independent corpus audits and preserved work

| Audit | Snapshot / finish (EST) | Heroes | Windows | Stems | Public objects | Duration / exit |
| --- | --- | --- | --- | --- | --- | --- |
| Initial | 18:46:10 / 18:47:22 | 25 | 7,910 | 104 | 454 | 72.234 s / host 1, nested count-shortfall caveat |
| Post task 11 | 18:53:34 / 18:54:51 | 26 | 8,015 | 108 | 458 | 77.687 s / propagated 2 |
| Final | 18:59:57 / 19:01:21 | 27 | 8,117 | 112 | 462 | 83.953 s / propagated 2 |

All snapshots: **350 library tracks + one excluded acceptance import**, zero invalid windows,
cache/DB issues or public audio failures. Final: **462 objects fully decoded/probed**, **458 local
hash anchors**; four on-demand files have public hashes without local expected-hash anchors. Public
format: stereo 44.1 kHz, 192k MP3. Target remains **80**, **53 short at the final independent snapshot**.
Library: 200 Freesound / 150 Jamendo. License counts unchanged: FS BY-3.0=28, BY-4.0=98, CC0=74;
Jamendo BY-3.0=34, BY-SA-3.0=116. Jobs done=5/error=7, all seven intentional Session-4 audit errors;
no queued/running jobs at the report snapshot. Unknown future errors must not be exempted.

Final report: `ingest/data/session6/report-final.json`, SHA256
`4823ddefcb981583be6e5a358a0aa6f41d7ced84b9f88fc77f0a0b0d6790a5e2`.
Report summaries/hashes are committed in `EVAL_SESSION6.json`. Initial database access failed in the
sandbox; approved rerun succeeded. The initial outer host returned 1 for a nested nonzero script;
post-task/final commands explicitly propagate `$LASTEXITCODE` and **returned 2**, not a full gate pass.

Original hero **uv PID 32252 / Python PID 30820** remain alive, original start **16:31:16/17 EST**:
`uv run --no-sync --project ingest --env-file .env python -m ingest.heroes --mode batch --limit 80`.
Logs: `ingest/data/heroes-batch-20261114-163116.{stdout,stderr}.log`, `ingest/data/heroes/heroes.log`.
Separate later log checkpoint **19:04:26 EST**: **29/80 complete, 14 rejected**, next `jam_1432420`
separating. Rolling ETA 11,773.659 s (~3 h 16 m), projected ~22:20 EST, contingent on future stalls/
rejections. This is not a fresh independent DB/object audit. Preserve all queues, locks and caches.
No worker daemon was started; no process/job was stopped, reset or restarted.

Final pre-commit PID check at **19:09:20 EST** still finds both original processes alive. Latest
separate log **19:07:31 EST**: **29/80 completed, 15 rejected**, next `jam_1378557` separating. New
rejection `jam_1432420` has the same feature-stage location but **unmeasured individual stem RMS**;
preserve and inspect it next session. The final independent audit above remains the 27-hero snapshot.

Read-only diagnostic decoded 20 files from five newly rejected heroes, applying the actual nominal
10 s / 5 s-hop / >=4 s terminal / excerpt-join rules. At least one stem has zero eligible audible
windows for every rejected hero. Maximum nominal-window RMS for zero-window stems:

| Hero | Stem | Maximum RMS |
| --- | --- | --- |
| jam_1149158 | bass | 0.0003227814 |
| jam_1207327 | vocals | 0.0007990852 |
| jam_1342553 | bass / vocals | 0.0015004515 / 0.0014478642 |
| jam_1378003 | vocals | 0.0006712934 |
| jam_1485349 | vocals | 0.0012409908 |

All are below the unchanged **0.0056234133 (-45 dBFS)** silence gate. Initial protected-cache decode
failed; approved rerun passed. Measurements/script/logs are in `ingest/data/session6/rejections*` /
`diagnose_new_rejections.py`, with measurements committed in `EVAL_SESSION6.json`. No gate was lowered,
no silent window invented and no cache/DB mutation made. Later failures require their own inspection.

## Exact checks and commands

| Check | Result |
| --- | --- |
| Focused initial eval | 31 passed / 2.27 s |
| Focused final eval | 36 passed / 2.43 s |
| Task 11 ingest / worker | 100 passed / 46.36 s; 23 passed, 5 skipped / 33.63 s |
| Final ingest / worker | 105 passed / 41.37 s; 23 passed, 5 skipped / 31.19 s |
| Python Ruff check / format-check | Pass; 61 files |
| make lint | Attempted twice; Make absent |
| pnpm --dir web lint / typecheck | Both fail before code checks: no matching @pnpm/exe@12.14.0 |

Five skips are existing opt-in real DB tests, not rerun. Common unchanged; common tests not rerun.
Initial test collection failed because the API package is not on ingest's import path; corrected by
reading the binding model module directly, with no API runtime dependency. Initial formatting errors
were fixed; final Ruff and all suites above pass. Generated audition browser playback is untested.

Tests from repo root: `uv run --project ingest pytest ingest/tests` and
`uv run --project worker pytest worker/tests`, with `-q --tb=short -p no:cacheprovider`, FFmpeg PATH,
workspace UV cache, OMP/MKL=2. Basetemps `ingest/data/pytest-session6-{task11,final}` and
`worker/data/pytest-session6-{task11,final}`. Focused: `ingest/tests/test_eval.py`, basetemps
`ingest/data/pytest-session6-eval{1,2,-final}`. Logs: `ingest/data/session6/{task11,final}-{ingest,worker}.*.log`.
Ruff: `uv run --project api ruff check common ingest worker api scripts` and `ruff format --check`
on the same paths. Only the new eval files were autoformatted; no unrelated source was changed.

Reports: `./ingest/launch-audit.ps1 -Mode report -Output ingest/data/session6/report-{task11,final}.json
-Foreground` with stdout/stderr redirected to corresponding `.stdout.log` / `.stderr.log`, followed
by `exit $LASTEXITCODE`. The initial report had terminal output; authoritative JSON is retained.
Completed automation sessions: initial report 99974; task11/final reports 94460/35473; eval attempts
94942/5244; suites 51206/77047/58930/39067; pnpm 54813. These are tool session IDs, **not OS PIDs**.
No continuing process besides the original hero batch is left by Session 6. pnpm created one new
8 KiB `.pnpm-store/v11/index.db`; removed only that generated file after path/creation checks,
preserving pre-existing directories. `git diff --check` passes; existing schema modification excluded.

Changed files: `ingest/eval.py`, `eval_queries.yaml`, `tests/test_eval.py`, `README.md`, `PLAN.md`,
`SESSION6.md`, `EVAL_SESSION6.json`, plus explicitly authorized `docs/codex-handoff.md`.
Unchanged contracts: APIs/schemas, IDs/storage paths, common helpers, dependencies, model defaults,
frozen vocabulary, root `.env`, resumability fingerprints and silence gate. Existing schema SHA256:
`BB8F20C0BA862279A7B89B12C3E2946AF087E43F10E1AE184132AC2E181F6DF5`.

Session 7 instructions are in the current top section of `docs/codex-handoff.md`. Do not mark either
eval task complete without live results, two attributed reviews and the required follow-up evidence.
