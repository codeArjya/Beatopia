# Proposal WS3-job-output: type `Job.output`

**Author:** WS3. **Status:** proposed. **Wire format change:** none (the JSON bytes stay the same).

## Why
`Job.output` is `dict | None`, so the generated TypeScript type is `{ [k: string]: unknown } | null`. That means
every client (WS3's stems drawer and import page, WS4's "Stems in editor") has to hand-check the shape of the stems or
analyze output. Today nothing checks that the worker's output matches CONTRACT §3; only `scripts/check_fixtures.py`
validates it, against the fixtures. If the worker writes a wrong shape (for example `{"stem": [...]}`), the
`/jobs/{id}` response still passes validation and the browser fails at runtime with "cannot read properties of
undefined".

## The change

### `api/app/models/api.py`
```diff
 class StemsResponse(BaseModel):
     job_id: str | None = None        # set when separation was queued
     stems: list[Stem] | None = None  # set when stems covering the range already exist

+class StemsJobOutput(BaseModel):
+    stems: list[Stem]
+
+class AnalyzeJobOutput(BaseModel):
+    track: TrackDetail
+
 class Job(BaseModel):
     id: str
     kind: Literal["stems", "analyze"]
     status: Literal["queued", "running", "done", "error"]
     progress: float
-    output: dict | None = None       # see CONTRACT §3 job output shapes
+    output: StemsJobOutput | AnalyzeJobOutput | None = None   # stems job → StemsJobOutput, analyze → AnalyzeJobOutput
     error: str | None = None
```
The two output models have different required keys (`stems` vs `track`), so Pydantic's default "smart" union picks
the right one. No discriminator field is needed, and the stored `jobs.output` JSON doesn't change.

### `docs/CONTRACT.md`
§3, the job output line:
```diff
-Job `output` shapes: `stems` → `{"stems": [Stem, ...]}`; `analyze` → `{"track": TrackDetail}`.
+Job `output` shapes: `stems` → `StemsJobOutput` `{"stems": [Stem, ...]}`; `analyze` → `AnalyzeJobOutput`
+`{"track": TrackDetail}` (models in §5; `GET /jobs/{id}` validates them).
```
§5, the same diff as `api/app/models/api.py` above (the `StemsJobOutput` and `AnalyzeJobOutput` classes plus the
`Job.output` line).

### Generated files (`make schema`, never hand-edited)
`shared/schema/api.schema.json` gains `$defs/StemsJobOutput` and `$defs/AnalyzeJobOutput`. `Job.output` becomes
`anyOf: [StemsJobOutput, AnalyzeJobOutput, null]`. `web/lib/types/api.ts` should come out as:
```diff
+export interface StemsJobOutput {
+  stems: Stem[];
+}
+export interface AnalyzeJobOutput {
+  track: TrackDetail;
+}
 export interface Job {
   id: string;
   kind: "stems" | "analyze";
   status: "queued" | "running" | "done" | "error";
   progress: number;
-  output?: {
-    [k: string]: unknown;
-  } | null;
+  output?: StemsJobOutput | AnalyzeJobOutput | null;
   error?: string | null;
 }
```

### Fixtures
**No change.** `job_running.json` (`output: null`), `job_done_stems.json` (`{"stems": [...]}`) and
`job_done_analyze.json` (`{"track": {...}}`) already match. `make check-fixtures` now validates their outputs
through the schema as well.

### `scripts/check_fixtures.py` (optional cleanup in the same PR)
The schema now covers the hand-written `JOB_OUTPUT` / `JOB_OUTPUT_KEY` check. That check can stay, since it's
harmless, or be removed:
```diff
-from pydantic import TypeAdapter, ValidationError
-
-from app.models.api import Stem, TrackDetail
...
-# CONTRACT §3 job output shapes (Job.output is an untyped dict in the schema).
-JOB_OUTPUT = {
-    "stems": TypeAdapter(dict[str, list[Stem]]),
-    "analyze": TypeAdapter(dict[str, TrackDetail]),
-}
-JOB_OUTPUT_KEY = {"stems": "stems", "analyze": "track"}
...
-        if model == "Job" and data.get("output") is not None:
-            kind = data.get("kind")
-            try:
-                out = JOB_OUTPUT[kind].validate_python(data["output"])
-                if JOB_OUTPUT_KEY[kind] not in out:
-                    errors.append(f"{name}.json output: missing key '{JOB_OUTPUT_KEY[kind]}'")
-            except (KeyError, ValidationError) as exc:
-                errors.append(f"{name}.json output ({kind}): {exc}")
```

## Effect on other streams
- **WS1 (worker):** no code change if the worker already writes the CONTRACT §3 shapes. A wrong shape now makes
  `GET /jobs/{id}` fail validation (500) instead of reaching the browser. Run one stems job and one analyze job through
  `/jobs/{id}` once after this lands.
- **WS2 (api):** `GET /jobs/{id}` builds `Job(**row)` as before. Pydantic now validates `output` into the typed models.
  Rows with `status != "done"` keep `output = null`. Re-run `make schema` and the API tests.
- **WS3 (web):** drops its `isStemsOutput` / `isAnalyzeOutput` runtime guards and narrows with `"stems" in output`
  (or by checking `job.kind`). Until this lands, WS3 keeps the guards in `web/lib/api/jobs.ts`.
- **WS4 (editor):** if it reads job output directly, it must handle `output` as
  `StemsJobOutput | AnalyzeJobOutput | null`. WS4 normally goes through WS3's hooks, so it's unaffected.

## Can it wait until the next gate?
**Yes.** Nothing on the wire changes. WS3 works today with runtime type guards that are tested against
`job_done_*.json`. It's worth landing before **H12** (go-live), because that's when real worker output first reaches
the browser and server-side validation would catch shape bugs.
