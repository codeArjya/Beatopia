# WS2 proposal: pin the CLAP model WS1 actually ingested with

**Author:** WS2 · **Status:** proposed · **Can wait:** no. Every API process (local and the H12 deploy) needs it.

**What.** Change the CLAP env vars to the checkpoint the library was ingested with (WS1, `0877d84`,
`ingest/CLAP_MODEL_REVIEW.md`), and add the revision pin that `common/clap.py` already reads:

```diff
--- .env.example
-CLAP_MODEL=laion/larger_clap_music
+CLAP_MODEL=laion/larger_clap_general
+CLAP_REVISION=ada0c23a36c4e8582805bb38fec3905903f18b41   # must match ingest + worker + api
```

Same change in CONTRACT §8. §4's `common/clap.py` signature block gets `CLAP_REVISION` next to `CLAP_MODEL`.
WS1 may prefer to move the default in `common/clap.py` itself (WS1's file); then only `.env.example` and §8 change.

**Why.** `common/clap.py` defaults to `laion/larger_clap_music`, but every row in `windows.embedding` was made
with `laion/larger_clap_general` @ `ada0c23…` (the human approved this switch for WS1). An API started from today's
`.env.example` embeds queries with the wrong model, so the cosine distances mean nothing and search quality
silently collapses. Nothing errors: both checkpoints output 512-d vectors.

**Evidence.** With the general checkpoint, "dusty soul keys" on the seed returns Rhodes/R&B/soul windows at cosine
0.41–0.47 (T3.1 live check, 2026-11-14).

**Meanwhile.** WS2 runs with `CLAP_MODEL=laion/larger_clap_general CLAP_REVISION=ada0c23a36c4e8582805bb38fec3905903f18b41`
set in the shell / local `.env`. The API startup log prints the model and revision (`clap warm (...)`).

**Affects.** WS1 (owns `common/clap.py`, ingest, worker), WS2 (api + deploy env). No schema or fixture change.
