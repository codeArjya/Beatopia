# Session 8: live evaluation and launch-readiness integration

2026-11-14–15 EST, ws1-data, starting commit 1118b804f19ac2ea9e5e688478507ec18a2cebf4.
The human approved the six-step plan before implementation or integration jobs. Work began after
HTTPS first responded. This is a partial launch-readiness result: the real worker paths are verified,
while hero count, semantic fixture, strict range validation and editor routing remain open.
After completing the joint review, the user explicitly replaced the original two-independent-reviewer
requirement with that completed joint review. The current review-collection requirement is satisfied.

## Verified outcomes

| Check | Evidence-backed result |
| --- | --- |
| API | https://45-77-216-35.sslip.io; health/chips/real hero details/OpenAPI 200. Revisions observed: 43ea7a61263b246c3e06af534a845bc5289a0a6a, then 56838aecd79c3e1a299a450b8e792be7ef0a2a26. |
| Model/search compatibility | WS2/user confirms general CLAP revision ada0c23a36c4e8582805bb38fec3905903f18b41. Revision source uses the same common.clap/L2 normalization and SQL import exclusion. All 95 returned windows were found in the DB with unit embeddings, matching tags/credits/public object paths. No independent runtime weight attestation. |
| Twenty-query baseline | Actual unchanged dataset; all 20 HTTP 200; 19 queries returned five results, q14 returned none. Runner exit 1, one technical failure. Baseline bracketed by revision 43ea7a6 probes; per-query revision headers are not recorded by this runner. No eval-after or relevance-improvement claim. |
| New 30-second job | b8b7cb59-e316-4abc-b154-cf92fa4bdfbf, jam_1307441 [5,35], htdemucs, done/1.0. No previous covering stems/jobs. 23 polls, approximately one second apart. Enqueue-to-terminal poll 22.750 s; DB timestamps 22.009521 s. |
| Actual inference | Operator supplied the matching deployed worker log: handler 20.89182137 s; inference 11.087572925 s; CPU; no fallback. Positive inference timing and source branch distinguish new separation from checkpoint reuse. Reported model_load_s=0.314063149 is the engine instance initial load and does not establish this job was cold. |
| Stem outputs/cache | All four requested-model outputs have coverage [5,35], decode/probe as 30 s, stereo 44.1 kHz/192k MP3. A narrower [10,20] POST reused them without a job; file-local playback [5,15]. Original full hero reuse also returned four stems without a job. |
| Import | Dedicated generated 8 s stereo WAV; job 631df075-73d8-42c8-936b-819ef25c45e7, track imp_430eb4b6. Done in 5.891 s to terminal poll; one finite unit-normalized 512-d window; metadata preserved; public normalized bytes decode at 44.1 kHz stereo/8 s. Two real search probes exclude imports, supported by inspected SQL. Private import URLs redacted from evidence. |
| Browser | User-requested local Playwright + installed Chrome opened https://beatopia-liart.vercel.app/, observed live chips/search calls and real results. Jazzi Girl other-stem media advanced within [164.919,171.606] and looped back to its start, readyState 4/no media error. This is playback evidence, not human sound-quality acceptance. |
| Corpus before new test objects | Final independent snapshot 04:20:14.979874 UTC Nov 15: 350 library tracks + six excluded imports; 67 heroes; 12,618 total DB windows, 12,615 library windows; 272 stem rows. All 67 heroes/9,562 density windows and 622 public objects verified, zero integrity failures. Exit 2 for target 80, short by 13. |
| Final refresh | Snapshot 05:09:47.987525 UTC Nov 15, finished 05:20:58.808888, 671.297 s: 350 library tracks + 11 excluded imports; 67 heroes; 12,642 total DB windows / 12,615 library windows; 284 stems. All 67/9,562 density windows and 634 public objects verified, zero integrity failures; 618 local hash anchors and 16 range objects without local anchors. Jobs: 18 done / seven exact intentional Session 4 errors, none queued/running. Propagated exit 2 for the unchanged hero target. Earlier snapshots preserved. |

## Remaining failures and owners

- WS2: three API-snapped intervals cross the artificial processed-audio join at 120 s:
  q05 rank 5 jam_1121408:mix:120000 [119.56,126.247];
  q06 rank 2 jam_1030279:mix:110000 [110.097,120.685];
  q16 rank 2 jam_1348228:mix:120000 [119.954,128.955].
  Original nominal DB windows respect the join. Preserve the corpus; repair result snapping in WS2.
- WS2: negative/reversed/past-end/61-second ranges returned 400, but 60.005 seconds returned 200.
  Inspected jobs.check_range allows 0.01-second slack above 60. The strict over-60-second gate fails.
- WS2 + WS1 curation: q14 house/120 BPM returned no results. DB has one house-tagged window and zero
  meeting the requested tempo filter; deployed search source has no Freesound fallback. No fabricated
  results, retagging, threshold change or relevance-zero substitution.
- WS4: actual editor URL /editor?track=fs_166649&start=10&end=20&stem=other fetched real metadata but
  loaded mix.mp3. Native-control playback advanced from 0 to 1.780005 s in the mix, instead of playing
  the cached other range file at local [5,15]. Screenshot/network/media evidence is under browser/.
  No API/data-only substitute is claimed for this failed browser gate. Browser job-poll UI remains untested.
- Human acceptance: Santiago & Arjya completed one joint consensus review, explicitly combining
  query/listening-intent match and displayed-tag accuracy without separate scores. All 95 supplied
  grades/notes match the saved run; 92 technically valid results have grade counts 2=32, 1=32, 0=28,
  mean 1.0434782609/2. The three held range scores are preserved but excluded from these statistics.
  User explicitly approved replacing the original two-independent-reviewer requirement with this
  completed joint review. Current review acceptance is complete; no extra baseline review is required.
  The score remains descriptive mixed feedback, not a separately measured pure query-relevance metric.
  Reviewer B stays blank; actual grades and immutable snapshots are retained in FINAL_SESSION8.json.
  At the user's request, recorded_at uses UTC submission time 2026-11-15T06:20:06+00:00; the original
  value 22:56pm and original file bytes are preserved. No original listening time was inferred.
- Unchanged quality gates: target 80; 30 audibly prominent/useful timbres; perceptual sparse/dense
  calibration; historical mixed-fixture cosine 0.186066 < 0.2. No new semantic-fixture pass.
  Optional two-model comparison, automatic selection and personalization remain cut.
- WS2 operations: worker image label 069411369305f7550e0ed1987491cf2a11ed4059 differs from its process
  BEATOPIA_REVISION 567279d63c37de408fe1aba4ff925bbfc3905584. Worker/common source matches the tested
  main merge. Record both identities; fix version stamping without treating it as a model mismatch.
  Checked-in compose mounts model caches but omits worker/data durability; confirm actual mounts and
  preserve checkpoints before any future recreation. No container/cache/job reset was performed.

## Listening instructions and prepared auditions

Use data/session8/eval-before/audition.html, or audition-technical-notes.html for the extra hold banner.
Listen only within returned data-start/data-end, grading against query/listen_for intent:
0 irrelevant, 1 partial match, 2 useful match. Tags are context, not ground truth.
95 results exist; q14 has none. Leave q05 rank 5, q06 rank 2, q16 rank 2 null for technical failures:
92 currently valid clips per reviewer. REVIEW_NOTES.md and review-exclusions.json tie holds to run/digest.
Preserve run_id/result_sha256/query_id/rank/window_id. Record identity, ISO recorded_at and listening notes.
The completed review is stored in reviewer-A.json, with B blank. User confirmed the grades combine
query match and tag accuracy. User approved this single completed joint review as the replacement
acceptance requirement. Preserve its mixed interpretation and do not duplicate scores into B.
joint-review-final.json validates every
run/digest/rank/window identity and preserves the three excluded technical scores. Mean 1.0435/2 is
descriptive only; no automatic numerical acceptance threshold exists.

Calibration replay used the independent 64-hero snapshot: 12,239 library windows, zero changed tags.
calibration.html contains 58 attributed windows, including 30 distinct hero prominent-timbre candidates
and low/high density examples. Numerical tags/density are unreviewed screening evidence.
candidate-auditions.html accompanies 20 proposed additional heroes from 50 eligible licensed Jamendo
mixes outside the original queue/completed/rejected IDs. Exact frozen-vocabulary vocal/bass/drum/melodic
cosines are screening only; actual four-part instrumentation needs listening. No new inference or
production was started for this shortlist, and the live/frozen queue was never changed.

## Producer completion and density recovery

Original hero uv 32252 / Python 30820 retained original commands/starts and finished naturally:
67 completed / 33 rejected out of the unchanged 100-ID queue, target 80. Logged remaining ETA did not
make the target attainable. Queue SHA256:
2bfe34247b61a8aeef5f746bb9b2a87588c843e8eaa72a1fd4ec643e759e22d6.
No additional hero batch/resumption/queue extension is approved by this session's plan.

Original density uv 28192 / Python 21740 exited after a real OperationalError on jam_1039379:
server closed the DB connection. The failed 65-hero sweep verified 64/9,066 windows and is retained
as density-follower-failure.json. It is not reclassified as expected or a successful sweep.
After verifying both old PIDs were absent, resumed the existing migration with original receipts:
uv 21728 / Python 33096, launched 23:16:48 EST, no live lock removal or producer restart.
Recovery completed 67/9,562 windows, 68 updates, zero failures, 114.281 s; producer was already finished.
Both producer and recovery follower subsequently exited; preserve every queue, failure, cache and receipt.

Original logs:
- ingest/data/heroes/heroes.log and heroes-batch-20261114-163116.{stdout,stderr}.log
- ingest/data/density-20261114-193827.{stdout,stderr}.log; session7/density-follow.json
- recovery density-20261114-231648.{stdout,stderr}.log; session8/density-recovery.json

Read-only canonical FFmpeg measurements cover 12 newly rejected candidates / 48 files since the
21 already measured in earlier sessions. Every new rejection has a zero-eligible-window stem under
unchanged -45 dBFS, 10 s/5 s hop/minimum 4 s terminal and excerpt-join rules. Preserve all rejected
files. Raw evidence: rejections.json. No fake windows, gain changes or threshold reductions.

## Worker main merge and deployment trace

At the user's follow-up request, integrated the existing Session 4 implementation from 643b883 into
main through an isolated worktree under data/session8/worker-main-integration:
worker-only commit 417556ddbd2ab19f1cdcf208912f72540f25158e, then main merge
018e0c7ea25087cf46e9c0f438a6ab0b207fef73. Exactly worker/ changed relative to concurrent main.
Incorporated teammate contract commit b7485cf without manual edits to shared files. Main remote SHA
was verified. No force push; a first non-fast-forward rejection preserved concurrent work.
GitHub connector PR creation returned 403; ordinary authenticated Git push performed the authorized merge.

The primary checkout stayed on ws1-data, preserving its schema edit. Worker/common trees match the
tested source. Isolated integration suite: 23 passed/5 opt-in skips in 24.98 s.
The operator's VM: beatopia-vultr-api, root/password SSH (no password collected), API revision 56838ae,
15 GiB RAM/13 GiB available, 8 GiB swap, 195 GiB free disk; initially API/Caddy only.
Agent key-only SSH failed. Prepared worker-only tar + bounded start script; operator uploaded it.
Image 018e0c7 built in 64.5 s, but up hit a name conflict with a concurrently running worker.
Kept that live container intact: beatopia-worker-1, reported container ID
9d8e57ed87880a5ad6b43075f5cf12345cef92804d362bacf6d74f58f99b3d0e, started
2026-11-15T04:50:53.714146507Z, image label 0694113, process revision 567279d.
Operator verified general CLAP/revision and CUDA unavailable. Inspected image source has no
worker/common diff from tested main. Real owned job timing proves CPU inference through that service.
No duplicate/local worker, container removal/rename, bulk reset or unknown-job polling was performed.

## Checks, diagnostics and preserved contracts

- Focused eval 36 passed/5.15 s; ingest 134 passed/74.31 s; worker 23 passed/5 skipped/48.38 s.
- Isolated main worker integration 23 passed/5 skipped/24.98 s. Five opt-in live tests were not rerun.
- Python Ruff check/format pass, 55 files. make lint attempted: Make is not recognized; no global lint pass.
  Common runtime source unchanged/parity checked, so no common rerun. No API/web checks or repairs claimed.
- Independent reports preserve explicit child exits. Pre-integration final audit took 667.094 s, exit 2;
  initial report took 4,237.110 s wall time across an unobserved tool/host interval, exit 2. Cause of the
  elapsed-time gap is not established; no constant-throughput or uninterrupted-monitoring claim.
- First provenance diagnostic misread UTF-8 using Windows default encoding and falsely flagged credits.
  Corrected UTF-8 comparison found zero credit mismatches; first-pass artifacts retained. No API/DB repair.
- Decoder diagnostic failed inside sandbox, then corrected a string-ID queue-reader assumption and exact
  vocabulary spelling; failures/measurements/earlier screen retained. These are diagnostic fixes, not
  corpus or relevance changes. Original eval/results/digests/dataset and human grades were not rewritten.
- Initial seven unrestricted health probes over 1,808.752 s all timed out; extension first worked at
  02:49:16.920117 UTC, revision 43ea7a6. Exact timestamps/HTTP/timing evidence are in connectivity*.json.
  Extended five-minute cadence had an unobserved gap during pending tool interactions; do not call it
  continuous coverage. Separate web/CUA tools failed; user-requested local Playwright completed UI checks.

Only four Session 8 tracked documentation/evidence files change in this checkout: ingest/PLAN.md,
SESSION8.md, FINAL_SESSION8.json and authorized docs/codex-handoff.md. Separate authorized main merge
contains existing worker code. Temporary Playwright tooling and all raw evidence remain ignored under
data/session8/. No API/web/deployment/shared-model/schema/environment/vocab/embedding-default edits.
Pre-existing shared schema SHA256 remains
BB8F20C0BA862279A7B89B12C3E2946AF087E43F10E1AE184132AC2E181F6DF5, excluded from commits.

## Exact next operator/session steps

1. Read this record, FINAL_SESSION8.json, PLAN, contract and current handoff. Inspect current branch/status,
   protected process IDs/commands/start times and logs before any resume. Original local jobs finished;
   verify rather than assuming. Leave the real VM worker running.
2. Keep job b8b7cb59-e316-4abc-b154-cf92fa4bdfbf and analyze job
   631df075-73d8-42c8-936b-819ef25c45e7 as completed audit rows. Do not reset or poll unrelated jobs.
   Private acceptance fixture imp_430eb4b6 stays excluded from search; do not print its URLs.
3. The joint mixed-feedback review is complete, snapshotted and accepted under the user-revised
   one-joint-review requirement. No additional baseline round is needed. Preserve the explicit
   criteria-change record instead of treating the original independence requirement as still open.
   After actual fixes, generate fresh result-bound review files; retain this baseline and technical
   exclusions. To revalidate this joint file offline, run the retained validate_joint_review.py helper
   under data/session8/. It does not request the API or modify human grades.
4. WS2 fixes snapping/strict >60 s validation/fallback and confirms actual model/process stamps; WS4 fixes
   editor stem/range routing. Only after justified fixes rerun the unchanged twenty-query dataset into
   a new eval-after directory, then collect fresh joint feedback under the revised requirement.
   Never transfer old grades to new results. A retry is not a gain.
5. Complete actual 30-track prominent-timbre and sparse/dense listening using the attributed auditions.
   Investigate the failed semantic fixture without changing the acceptance score.
6. Review the additional-candidate shortlist before any new production; preserve the exhausted original
   100-ID audit/queue and all checkpoints. Keep target/cap 80. No automatic production extension here.
7. Fresh audits use the cached launcher environment and a new output path; explicitly exit $LASTEXITCODE.
   After new implementation run focused tests, make lint (or exact failure/equivalents), ingest/tests,
   worker/tests, common if changed, and independent report. Always choose fresh workspace basetemps.
8. Before any VM worker recreation, confirm durable checkpoint storage with WS2. Preserve the live worker,
   its receipts and model caches. Current agent SSH access is not configured; operator uses password SSH.
