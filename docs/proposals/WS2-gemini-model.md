# WS2 proposal C9: `GEMINI_MODEL=gemini-3.6-flash`

**Status:** proposed (2026-11-14). **Affects:** `.env.example`, CONTRACT §8. Only WS2 reads `GEMINI_MODEL`.

## What
```diff
-GEMINI_MODEL=gemini-3.8-flash         # newest stable Flash on ai.google.dev as of 2026-11-14
+GEMINI_MODEL=gemini-3.6-flash         # fast + available; 3.8 Flash was overloaded (503) and slower, see WS2 proposal C9
```

## Why (measured live on 2026-11-14 with the team's key, full P1 planner prompt)
| Model | Thinking | Planner latency | Notes |
| --- | --- | --- | --- |
| `gemini-3.8-flash` | LOW (rejects MINIMAL) | n/a | 503 "high demand" / 504 on every call, also on a 3-word prompt |
| `gemini-3.7-flash` | — | n/a | 503 on every call |
| `gemini-3.6-flash` | MINIMAL | **1.0–1.6 s** | correct plans on all test queries |
| `gemini-3.6-flash` | LOW | 2.7–10.8 s | too slow for `/search` < 3 s |
| `gemini-3.5-flash-lite` | MINIMAL | 9–11 s | |
| `gemini-3.1-flash-lite` | MINIMAL | 1.2–11.7 s | |

`/search` has a 3 s p50 target, and the planner and rerank are both on that path. 3.8 Flash would also be forced to
thinking `LOW`. The code handles either model (MINIMAL is sent as LOW to 3.8 Flash), so this is only a default change.

Separately, the current local `.env` says `GEMINI_MODEL=gemini-3.8-flash-lite`, which does not exist (404). Every
Gemini call fails with that value, so it has to change either way.

## Meanwhile
WS2 runs live checks with `GEMINI_MODEL=gemini-3.6-flash` set in the process env. The code default stays
`gemini-3.8-flash` (CONTRACT §8) until this lands.
