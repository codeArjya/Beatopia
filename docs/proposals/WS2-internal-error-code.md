# WS2 proposal: `internal_error` code for unhandled 500s

**Author:** WS2 · **Status:** landed by the `contract: C7–C9` PR (2026-11-15)

**What.** Add `internal_error` (HTTP 500) to CONTRACT §6 "Error codes in use".

**Why.** CONTRACT §5 says every non-2xx body is `{"error": ApiError}`. An unhandled exception (a bug) currently has
no code in the list. Without a handler, FastAPI returns a plain-text `Internal Server Error`, and the web client's
error parser breaks on it. The API now returns `{"error": {"code": "internal_error", "message": "something went
wrong on the server"}}` and logs the traceback.

**Affects.** WS3/WS4 only if they switch on `code`: treat `internal_error` like `upstream_error` ("try again").
No model, schema or fixture changes (`ApiError.code` is already `str`).

**Assumption meanwhile.** WS2 returns `internal_error` for unhandled exceptions.

## Diff

```diff
--- a/docs/CONTRACT.md
+++ b/docs/CONTRACT.md
@@ §6
 Error codes in use: `not_found`, `bad_request`, `range_too_long`, `clip_is_sliced`, `upload_too_large`,
-`unsupported_format`, `upstream_error` (Gemini/Freesound), `rate_limited`.
+`unsupported_format`, `upstream_error` (Gemini/Freesound), `rate_limited`, `internal_error` (unhandled server bug, 500).
```
