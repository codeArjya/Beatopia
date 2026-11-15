# Session 7: hero activity density and final acceptance record

2026-11-14, `ws1-data`, starting commit `d2b86f3498138e3eb8c8d5b037043faf696ad9f0`.
The human reviewed and approved the Session 7 plan before implementation. Scope is original refined
tasks **13–14**. The optional model comparison is cut because core gates remain open. Required
density work is implemented; final acceptance evidence below will identify the exact audited snapshot.

## Implementation and recovery contract

`ingest/density.py` measures the existing hero formula on all five audio streams: equal-weight mean
of spectral flatness and the fraction of the four full stems whose stereo RMS is strictly above
`10**(-30/20)`, clipped to [0,1]. Mixes are migrated from their original onset proxy; existing stem
densities must already agree with decoded measurements. The -45 dBFS window-eligibility gate,
nominal ranges and artificial excerpt joins are unchanged. Nonhero density is unchanged.

Each hero is validated against its exact mix/model/vocab identity, audio hashes, full stem rows,
window set, vectors, tags and other features. A local `stem-activity-density.json` receipt binds the
inputs, original mix densities and measured values for every mix/stem window. DB updates change only
`windows.density`, transactionally per completed hero. Atomic replacement of the mix manifest follows
commit. A crash between those steps is visible in reporting and can be repaired by rerunning the same
command/receipt without separation, embedding, upload or re-tagging. Changed inputs are rejected.
The existing pipeline validator checks migrated mix values/provenance, so ordinary resume retains them.

`-Follow` uses a separate density lock and observes the existing producer lock without modifying it.
It sweeps completed DB heroes, sleeps 30 seconds, and performs a final sweep after producer shutdown.
Any failed track is recorded and exits 1. It does not restart/stop the producer or reset jobs/caches.
Coverage applies to an explicit DB snapshot; future heroes may await the next follower sweep.

The reporter independently re-decodes all five files using the canonical FFmpeg decoder, recomputes every hero window,
and compares both DB and receipt values. Missing migration is incomplete (exit 2); damage/mismatched
measurements are failures (exit 1). `all_completed_hero_density` is separate from the 80-hero target,
formal timbre listening, semantic CLAP gate and actual HTTP relevance/integration acceptance.

### Investigated live verification failure (no tolerance relaxation)

The first migration snapshot contained **32 heroes**. It committed density updates and manifest
receipts, then **all 32 failed post-write verification**, exit **1**, **482.359 s**, Python PID **30988**.
Its summary records zero verified heroes, not successful acceptance or zero writes. Original failure
evidence is preserved as `ingest/data/session7/density-initial.json` and sibling
`session7-density-initial.*.log`. The process exited itself; the original hero producer was untouched.

Read-only investigation found server **`extra_float_digits=0`**: text retrieval rounds PostgreSQL
`real` to six significant digits. On `jam_1030277`, text maximum delta was **5.118097216039175e-7**,
with **139** values outside the migration's **1e-7** check. Binary retrieval of the same committed
values gave maximum delta **2.962769940495491e-8**, **zero** failures. Stored values were correct.
Both migration reads and the reporter snapshot now request psycopg binary results. The tolerance
is unchanged. The regression test simulates lossy text retrieval and demands binary float32 reads;
ordinary cache/audio fingerprints and acceptance thresholds remain unchanged. Diagnostic scripts/logs:
`ingest/data/session7/diagnose_density.py`, `session7-density-{diagnostic,precision}.*.log`.

The resumed follower reuses these receipts without inference, validates the existing DB writes,
and reports zero updated rows for already migrated tracks. Its first and later sweep evidence and
independent reports are recorded below. Additional checks reject mismatched DB stem/track fields.

### Investigated independent-audit failure (canonical decoder and snapshot evidence)

The first post-task report snapshot **19:40:43 EST**, finished **19:47:07**, **384.485 s**, observed
**exit 1**, had **35 hero flags / 8,996 windows / 144 stems / 494 public objects**. Public objects all
passed. It verified density for **32 heroes / 4,576 windows** and correctly did not claim the full gate.
Three density failures came from using a different MP3 decoder for feature recomputation: libsndfile
and canonical FFmpeg produce slightly different decoded samples/flatness. Actual differences above
the existing **1e-5** feature tolerance were **2 drum windows** on `jam_1101341` (max
**1.2853648513555527e-5**), **one** on `jam_1222581` (**1.163780689239502e-5**), and **17** on
`jam_1433978` (max **1.2810342013835907e-5**). Shapes, coverage and sample rates were aligned.
No target was waived or tolerance increased. The final independent density audit re-decodes the bytes
with FFmpeg, the same canonical decoder used to generate the features; it does not trust receipts.
Independent libsndfile public decode and FFprobe format checks remain in place. Diagnostics:
`ingest/data/session7/{investigate_report.py,report-task14.json}` and sibling
`session7-report-{task14,diagnostic}.*.log`.

The fourth issue was a real snapshot race on `jam_1544392`: DB snapshot saw a nonhero with its original
mix density, then the running batch promoted it and the follower migrated its cache. For a **nonhero
snapshot only**, the reporter now compares every mix window/vector/feature against the receipt's exact
recorded original densities, and exposes `density_migrated_after_snapshot=true`. Missing/invalid
original evidence still fails. A hero snapshot cannot use this fallback. This does not label the old
onset proxy as stem density or skip a comparison. Regression tests cover both snapshot states.

After these corrections, focused **64 passed / 45.74 s**, ingest **134 passed / 62.69 s**, worker
**23 passed, 5 skipped / 39.21 s**, all exit **0**. Logs use `session7-canonical-*`; fresh basetemps
use `pytest-session7-canonical-*`. `make lint` was attempted again (Make absent). Final Ruff and
independent report outcomes follow below; no changed source acceptance is inferred from the earlier
precision-only suites.

Final Ruff check/format-check passed, **65 files**. A two-character-overlength test line failed the
first canonical lint run, then formatting that line corrected it; no behavior/assertion changed.
Both failed and successful logs are retained as `session7-canonical-{ruff,format}[-fixed].*.log`.
The successful outputs are included verbatim in FINAL_SESSION7.json. Tests were not needlessly
repeated after this whitespace-only correction.

## Checks recorded before live migration

| Check | Result |
| --- | --- |
| First focused density/report/heroes run | 58 passed, 1 failed / 32.28 s |
| Corrected focused rerun | **61 passed / 25.39 s** |
| Ingest suite | **131 passed / 58.85 s** |
| Worker suite | **23 passed, 5 skipped / 35.41 s** |
| Python Ruff check and format-check | **Pass; 64 files** |
| `make lint` | Attempted; Make is absent, so no global lint pass |

The initial failure was a test-fixture alias: its simulated DB embedding shared the expected array.
The fixture now copies the DB vector, so corrupting DB data leaves expectations independent. No
acceptance assertion was relaxed. Tests cover strict stereo activity, missing/misaligned/nonfinite
inputs, joins/ranges, changed stem measurements, stale receipts, decoded-audio tamper detection,
unrelated DB changes, post-commit crash recovery, repeat idempotency, producer-lock preservation,
follower shutdown/failure and explicit incomplete coverage. Five existing opt-in live DB tests were
not rerun; their Session 4 evidence remains historical. Common helpers unchanged; no common rerun.

Commands: repository-root `uv run --project ingest pytest ingest/tests` and `uv run --project worker
pytest worker/tests`, with `-q --tb=short -p no:cacheprovider`, cached FFmpeg PATH, workspace UV cache,
OMP/MKL=2 and fresh `*/data/pytest-session7-final` basetemps. Focused basetemps are
`ingest/data/pytest-session7-focused{,-fixed}`. Test logs are
`ingest/data/session7-{focused,focused-fixed,ingest}.*.log` and `worker/data/session7-worker.*.log`.
Ruff logs: `ingest/data/session7-{ruff,format}.*.log`. Web checks were not rerun; no global lint pass
or web/API repair is claimed. Previous pnpm bootstrap failure remains recorded in Session 6.

After the precision fix and explicit DB stem/track checks: focused **63 passed / 35.58 s**, ingest
**133 passed / 57.19 s**, worker **23 passed, 5 skipped / 35.39 s**. Final Python Ruff check and
format-check pass (**64 files**). `make lint` was attempted again and still cannot start. Logs use
`session7-precision-{focused,ingest,ruff,format}.*.log` under ingest/data and
`worker/data/session7-precision-worker.*.log`; fresh basetemps use `pytest-session7-precision-*`.
The corrected suites exited **0**. No common helper or dependency change, so common tests were not
rerun. Existing API/web tests were not altered to hide the unavailable global lint toolchain.

## Initial independent audit

Read-only snapshot **19:19:54 EST**, finished **19:21:10**, **76.594 s**, propagated **exit 2**:
**350 library tracks + one excluded import, 31 heroes, 8,589 windows, 128 stem rows**. All **478 public
objects** decoded/probed successfully, zero invalid windows/cache-DB/public failures; target 80 is
**49 short**. This audit ran before density migration. Initial sandbox DB access failed with
OperationalError; the approved retry succeeded. Failed and successful logs are preserved under
`ingest/data/session7-report-initial[-confirmed].*.log`.

## New rejection measurements

Read-only libsndfile decode of **12 files** for **jam_1131022, jam_1378557, jam_1432420** confirms that
each has at least one zero-eligible-window stem using the original nominal 10 s/5 s-hop/minimum-4 s
terminal-window and join rules. Zero-window maximum RMS values:

| Hero | Stem | Maximum nominal-window RMS |
| --- | --- | ---: |
| jam_1131022 | bass | 0.0002364002362808554 |
| jam_1131022 | vocals | 0.00019153405575251297 |
| jam_1378557 | vocals | 0.0005746322850828993 |
| jam_1432420 | vocals | 0.0017265033491215768 |

All are below unchanged **0.005623413251903491**. No threshold change, invented windows or repair.
The first protected-cache attempt failed, then approved read-only decode passed. Exact measurements,
events and script: `ingest/data/session7/{rejections.json,diagnose_rejections.py}`, with sibling
`session7-rejections[-confirmed].*.log`. Later failures need their own inspection.

One later failure, **jam_1149162**, was independently decoded too: vocals have zero eligible windows,
maximum nominal RMS **0.0002283764726849405**. Final diagnostic contains **16 decoded files / four
new rejected heroes**, with the prior twelve-file snapshot preserved in `rejections-initial.json`.
Final stdout/stderr are `session7-rejections-final.*.log`. No new measurements are inferred for any
failure occurring after this diagnostic's recorded events.

At **20:32:05 EST**, the refreshed diagnostic decoded **24 files / six newly rejected heroes**,
including later `jam_1364453` vocals max nominal RMS **0.00009037725697345867** and `jam_1501360`
vocals **0.0016582880159251095**, both zero eligible windows below the same gate. The preceding
four-hero evidence is preserved as `rejections-four-heroes.json`; latest output/logs are
`rejections.json` / `session7-rejections-last.*.log`. All six new failures are measured; failures after
that event snapshot must be reported separately until investigated.

## Explicit cuts and remaining gates

- Task 13's two-model comparison is **not conducted**: core hero, semantic, formal listening and
  live-query gates have not passed. No cross-correlation, residual-energy, CLAP label-comparison,
  model winner or per-job model selector is claimed. No second-model inference/download or doubled
  job work. Existing supported requested-model semantics remain unchanged.
- The target remains **80**, with all four stem streams embedded; no reduction to 40 or skipped
  vocals/drums acceptance. FMA remains excluded; 200 Freesound/150 Jamendo library is preserved.
- The mixed-fixture general-CLAP score **0.186066 < 0.2** remains a recorded failure. Per-process
  general model revision is unchanged; WS2 matching deployed query weights remains unverified.
- This checkout still unconditionally serves `/search` fixtures (`api/app/main.py:90–91`), and no
  actual live URL/revision has been supplied. Session 6's two twenty-query runs timed out; those are
  historical network attempts, not new Session 7 results. No relevance grades or before/after gains
  exist. The user and teammate remain the designated independent reviewers.
- One identified Session 5 track/stem listening review remains one. Thirty prominent useful timbres,
  sparse/dense perceptual calibration and actual browser polling/range playback remain unverified.
- Historical real 30 s CPU job **47.608574 s** enqueue-to-terminal-poll, handler **46.208013 s**,
  inference **29.384854 s**, passed once in Session 4. Session 3 local inference was **33.183462 s**
  for 30 s and **207.197166 s** for 180 s, excluding pipeline work. No new benchmark or GPU pass is
  claimed. H0 is unspecified, so absolute elapsed H gates are not asserted.

Final independent density/report evidence, preserved process checkpoint and recovery instructions
are recorded in the final section below and `docs/codex-handoff.md`.

## Corrected independent acceptance snapshot

`ingest/data/session7/report-canonical.json`: snapshot **19:58:57 EST**, finished **20:07:15**,
**498.266 s**, observed propagated **exit 2**. **350 licensed library tracks + one excluded import,
40 complete heroes, 9,492 windows, 164 stem rows**. All **40 completed heroes / 5,576 mix-and-stem
windows** independently re-decoded and measured; `all_completed_hero_density=true`, no missing heroes.
Maximum DB density delta **2.9802322387695313e-8** (float32 storage), maximum receipt delta **0.0**.
Zero invalid windows, cache/DB issues, density mismatches or public failures. All **514 public objects**
decoded/probed; **510** have local hash anchors, four on-demand range objects have public hashes but
no local hash anchor in this reporter. This verifies the canonical-decoder correction on all heroes,
including the three previously failing decoder comparisons. No tolerance or gate was relaxed.

Target **80 remains 40 short** at this snapshot; exit 2 is not full-quality acceptance. Jobs remain
**done=5/error=7**, all seven exact intentional Session 4 errors, no queued/running jobs. Library is
200 Freesound/150 Jamendo; licenses are unchanged. Raw report SHA256:
`ff8e837edc8b04f1ac7330308a9ef030e8abc021f318ab6a59ec472e86f6a327`.
This audit finished while the session was paused awaiting continuation. The producer and density
follower continued; their later counts are separate evidence. A fresh final report is retained below.

Compact evidence is generated from retained artifacts by `ingest/data/session7/summarize.py` into
`ingest/FINAL_SESSION7.json`; it includes source hashes, raw test outputs, every audited hero's receipt
hash, failed attempts, job errors, rejection measurements and explicit cuts. The first summarizer
attempt failed on PowerShell UTF-16 output logs; BOM-aware reading corrected it without changing
any evidence. Both failed/successful generation logs are retained as `session7-evidence-*.*.log`.

## Final independent audit and preserved process checkpoint

Final snapshot **20:33:31 EST**, finished **20:43:26**, **595.562 s**, observed propagated **exit 2**:
**350 library tracks + one excluded import; 48 complete heroes; 10,365 total windows; 196 stem rows**.
All **48 heroes / 6,701 mix-and-stem windows** independently re-decoded and measured;
`all_completed_hero_density=true`, no missing hero IDs. Max DB density delta
**2.9802322387695313e-8**, receipt delta **0.0**. **Zero invalid windows, cache/DB/density errors or
public-object failures**. All **546 public objects** decode/probe correctly; **542** local hash anchors,
four on-demand range objects without local anchors. Source/license counts unchanged: FS BY-3.0=28,
BY-4.0=98, CC0=74; Jamendo BY-3.0=34, BY-SA-3.0=116. The three import windows are excluded from library
window counts. Library windows: mix=5,219, bass=1,322, drums=1,441, other=1,536, vocals=844.

Jobs **done=5/error=7**, all seven retained intentional Session 4 audit errors; no queued/running jobs.
Target remains **80**, **32 short** in this audit; full-quality/global-lint/listening/live-eval checks
remain unverified. Task rows stay unchecked for the unverified combined acceptance, while required
density and final-handoff evidence are explicitly complete at this snapshot. No score or window is
invented and no conditional comparison pass is claimed.

Authoritative UTF-8 JSON: `ingest/data/session7/report-final.json`, SHA256
`00bce91f047a5b7e77564b9aaf1942bd3339c8fafa3c1fc8dac3c843870d6d51`.
Command: `./ingest/launch-audit.ps1 -Mode report -Output ingest/data/session7/report-final.json
-Foreground` with `> ingest/data/session7-report-final.stdout.log 2>
ingest/data/session7-report-final.stderr.log; exit $LASTEXITCODE`. The tool session **45579** finished
with exit **2** and is not an OS PID. The earlier corrected report independently passed the same
density/integrity checks at 40 heroes, so repeat audit evidence is retained rather than overwritten.

At **20:43:31 EST**, all four original/start-verified processes were alive: hero uv **32252**
(16:31:16.865 EST) / Python **30820** (16:31:17.016), follower uv **28192** (19:38:27.528) / Python
**21740** (19:38:27.673). `processes-final.json` and FINAL_SESSION7.json retain exact timestamps.
Latest separate producer progress was **49 complete / 21 rejected**, target 80, logged rolling ETA
**6522.885 s**. This is not an achievable target ETA from the existing queue: the verified capacity
ceiling is 79. Latest completed follower sweep **20:42:55 EST** verified **49 heroes / 6,870 windows**,
**zero updated rows**, **zero failures**, **71.297 s**. These later migration/log counts are separate
from the independent **48-hero** public-object snapshot. Only producer and follower remain running;
all Session 7 audit/test/diagnostic commands have finished. No worker daemon, process restart/stop,
job reset, queue edit or cache deletion occurred.

Later evidence-release checkpoint **20:46:18 EST**: producer progress **50 complete / 21 rejected**;
follower sweep **20:46:13** verified **50 heroes / 7,037 windows**, **34 updated rows**, zero failures.
FINAL_SESSION7.json retains those later values and their exact timestamps. The independent final
public-object audit remains the explicitly frozen **48-hero** snapshot; neither count is substituted
for the other. No further report or test rerun is needed without a new change/failure.

Artifact consistency check `ingest/data/session7/verify_evidence.py` passed (exit 0): exact final
counts, audit/receipt coverage, every retained report/receipt/test-output hash, preserved schema,
observed exits, known job classifications and explicit cuts. Logs `session7-evidence-verified.*.log`.

### User's follow-up estimate for 100 heroes (not a configuration change)

At **20:48:34 EST**, latest progress was **51 completed / 21 rejected**, elapsed **15,381.824 s**;
the last ten newly published heroes averaged **226.145 s** each (range **94.593–286.496 s**), excluding
failed-candidate time. Observed acceptance is **51/72 ≈ 70.8%**. A planning estimate for 49 more heroes
is roughly **70 more candidate attempts** at that rate, with only **28** frozen-queue candidates left:
about **42 additional candidates** beyond that queue. Allow roughly **4–5 further processing hours**
at observed overall throughput, plus discovery/indexing time. These are estimates, not a pass/time
promise; the candidate tail may have a different hit rate. The existing run remains configured for
**80**, and the queue can produce at most **79**. No target/CLI cap or running queue was changed.

To improve prospective hit rate without relaxing acceptance: rank licensed full mixes with evidence
of actual vocals, bass, drums and melodic accompaniment; exclude proven quiet-stem failures from
blind retries; pilot new candidates and measure the actual success rate. Short separation probes
across multiple sections can prioritize candidates before full processing; a quiet opening does not
prove the rest of the song lacks vocals. Tag-based ranking/probes remain screening heuristics, not
audible-window or prominent-timbre acceptance. New candidates and a 100-hero run require a separately
reviewed extension after preserving the existing batch, not a silent change to Session 7's targets.

Latest rejection measurement (**20:41:07 EST**) decoded **28 files / seven new rejected heroes**;
`jam_1432368` vocals have zero eligible nominal windows, max RMS **0.00021213193478765186**. Every
new rejection measured in this session has a real quiet-stem explanation. Six-hero snapshot retained
as `rejections-six-heroes.json`; latest logs `session7-rejections-latest.*.log`. Any failure after this
measurement snapshot needs its own investigation. Existing failed jobs remain classified separately.

## Changed files and preserved contracts

Changed WS1 files: `ingest/{density.py,pipeline.py,report.py,launch-audit.ps1,tests/test_density.py,
README.md,PLAN.md,SESSION7.md,FINAL_SESSION7.json}`. The human explicitly authorized updating
`docs/codex-handoff.md`. No API/web/common/worker runtime, schema, migration, ID, storage path,
model-default, frozen-vocabulary or dependency change. The pre-existing shared schema modification
is preserved and excluded; SHA256 remains
`BB8F20C0BA862279A7B89B12C3E2946AF087E43F10E1AE184132AC2E181F6DF5`.
The original ingest/hero queues, request budgets, source provenance, fingerprints, raw stems,
failed candidates, live producer and all existing jobs remain intact.

At **20:40:43 EST**, the preserved hero queue was verified to contain **100 distinct IDs**. Its
latest progress had **49 completed / 21 rejected**. Therefore even success on all 30 remaining
candidates could produce at most **79**, below the unchanged **80** target; later rejections can
only reduce that upper bound. Do not present the rolling ETA as a promise to reach 80. The producer
continues unchanged, and genuinely eligible additional candidates are required after this frozen
run. Preserve the original audit/queue before any later reviewed re-audit or candidate additions;
do not mutate the live queue, bulk-reset failures, or relax the four-stem/audible-window gate.

## Exact operational follow-up after Session 7

1. Read the current handoff, this file and PLAN; inspect git status/current commit. Preserve the
   unrelated schema edit. Do not interpret a later log count as the independently audited snapshot.
2. Check original hero uv/Python **32252/30820**, follower uv/Python **28192/21740**, and their log
   tails. Do not start duplicate processes or remove a live lock. Original hero logs are
   `ingest/data/heroes-batch-20261114-163116.{stdout,stderr}.log` and `heroes/heroes.log`.
   Density logs are `ingest/data/density-20261114-193827.{stdout,stderr}.log`; latest sweep is
   `ingest/data/session7/density-follow.json`. The follower exits itself after a final sweep when the
   producer releases its lock. If a machine restart changes PIDs, verify command/start time too.
3. If the density writer is confirmed dead, inspect its errors before resuming:
   `./ingest/launch-audit.ps1 -Mode density -Output ingest/data/session7/density-recovery.json -Follow`.
   If producer is already finished, use `-Foreground` without `-Follow` for a one-shot final sweep.
   Reuse the receipts; never delete them or reset fingerprints to suppress a mismatch.
4. Only if the original hero producer is confirmed dead and the target remains short, inspect the
   retained failures/queue/cache, then resume interrupted work with
   `./ingest/launch-heroes.ps1 -Mode batch -Limit 80`. Known quiet-stem failures stay failures; an
   exhausted frozen queue may need additional genuinely eligible candidates. Do not lower gates or
   rewrite a live queue. After any new producer run, start a density follower only if the old one
   has finished. The library ingest is finished; no library restart is needed.
5. Fresh audit (propagate the exit):
   `./ingest/launch-audit.ps1 -Mode report -Output ingest/data/session7/report-followup.json -Foreground`.
   In PowerShell automation append `exit $LASTEXITCODE`. Exit 1 is an integrity/operational failure;
   exit 2 is incomplete target/density acceptance. Read the explicit fields before claiming a pass.
6. No worker daemon was started. For an actual crashed running job, first confirm the former worker
   is dead, inspect that job ID's cache/error, then explicitly requeue **only that ID** per
   worker/README.md. Never bulk-reset the seven intentional error rows or a live running job.
7. WS2 must provide a real API URL/revision, matching approved general CLAP model/revision and import
   exclusion. Then run `uv run --project ingest python ingest/eval.py --base-url <actual-URL>
   --output-dir ingest/data/session7/eval-live`; collect independent user/teammate grades using the
   exact README commands. Do not run fixture search as live relevance or invent before/after grades.
   WS2/WS4 still own actual one-second HTTP polling and nonzero-range browser playback verification.
8. Complete formal 30-track timbre and sparse/dense listening with identified humans. Revisit the
   semantic fixture failure without a magic score. Optional two-model comparison remains behind all
   core gates; if they eventually pass, use supported requested models on a held-out set and record
   cross-correlation, residual energy, CLAP label similarity, actual timings and listening before any
   per-job selection. The final-session cut is not a quality-comparison pass.
9. After new implementation run the required focused/ingest/worker checks, common if helpers change,
   `make lint` (or record its environment failure), and reporting. Add new evidence rather than
   overwriting the recorded Session 7 snapshots. No automatic Session 8 work was launched.
