# WS2 proposal: a Freesound fallback trigger that can fire (C10)

**Author:** WS2 · **Status:** landed by the `contract: C10` PR (2026-11-15; WS3 agreed). Implemented in WS2 T8.1.

**What.** Replace the §7.7 trigger "fewer than 3 results have score > 0.25", and say where Freesound results go in
the list.

**Why.** The current trigger can't fire. The non-`sim` terms of §7.4 give every window a floor of about
0.2 + 0.6·sim, and CLAP text–audio similarity is rarely below 0.15. So every query gets 8 results above 0.25, even
"dog barking". I measured the top-3 `sim` on the dev library (350 tracks, `laion/larger_clap_general`):

| Queries | 3rd-best `sim` |
| --- | --- |
| The 20 WS2 eval queries (all fine in the library) | 0.318 – 0.504 |
| Non-music sounds: dog barking, rain on a tin roof, glass breaking, typewriter, car alarm | 0.158 – 0.302 |
| Instruments the library has no tag for: kazoo, didgeridoo, theremin, throat singing | 0.41 – 0.47 |

`sim` separates the sound effects. It doesn't separate an instrument the library lacks: CLAP happily matches
"kazoo orchestra" to other buzzy music at 0.44. The planner already sees the tag vocabulary, so it can say which
requested sounds aren't in it.

**Change.**
1. The fallback runs when **either**
   - *weak library match:* fewer than 3 candidate windows have `sim ≥ 0.30` (after the hard filters); or
   - *vocabulary gap:* the request names an instrument or sound that is not in the tag vocabulary, for example
     "kazoo". The Gemini planner reports these (WS2-internal; `SearchPlan` doesn't change), and the server drops
     anything that *is* in the vocabulary. Chips-only searches never have a gap.
2. Freesound is queried with the missing sound names on a gap, else with the request text. Freesound ANDs the
   words: "kazoo orchestra" finds 0 sounds and "kazoo" finds 102.
3. Only CC0 and CC BY sounds are used (the same license set as WS1's Freesound ingest), 1–30 s long.
4. **Freesound results come first**, then library results fill the rest (at least `limit // 4` of them when there
   are enough). The trigger means the library has no good match, so the Freesound sounds are what was asked for.
   A Freesound result's `score` reflects its Freesound rank (`0.5 − 0.02·rank`), not CLAP. So on a fallback
   response the list isn't sorted by `score`. The web client doesn't sort by score today.
5. `fallback_used = true` when Freesound was queried, even if it found nothing (as in `search_empty.json`). If
   Freesound is down or has no key, the library results are returned with `fallback_used = false`.

**Affects.**
- WS3: results can be Freesound-first. The existing `fallback_used` banner and the fixtures already cover this.
- WS4: no change. Fallback tracks already have `bpm: null` and `beat_times: []`.
- WS1: none.
- No model, schema or fixture changes. `plan_cache.plan` gains a WS2-internal `missing_sounds` key next to the
  `SearchPlan` fields (the column is `jsonb`; only WS2 reads it).

**Assumption meanwhile.** WS2 implements exactly this (T8.1).

## Diff

```diff
--- a/docs/CONTRACT.md
+++ b/docs/CONTRACT.md
@@ §7
-7. If fewer than 3 results have score > 0.25 → Freesound fallback, normalized into `Result` (`track.source = "freesound"`,
-   id `fs_{id}`, window id `fs_{id}:mix:0`, `audio_url` = Freesound `preview-hq-mp3`, window `0..min(duration, 16)` s,
-   `fallback_used = true`). Fallback tracks are **not stored** in v1 (not even when picked): `GET /tracks/{id}` and
+7. Freesound fallback when fewer than 3 candidates have `sim ≥ 0.30`, or when the planner finds that the request names
+   an instrument/sound outside the tag vocabulary (Freesound is then queried with those names, else with the request
+   text; CC0 and CC BY only, 1–30 s). Freesound results are normalized into `Result` (`track.source = "freesound"`,
+   id `fs_{id}`, window id `fs_{id}:mix:0`, `audio_url` = Freesound `preview-hq-mp3`, window `0..min(duration, 16)` s,
+   `score = 0.5 − 0.02·rank`), listed **before** the library results that fill the rest of `limit` (so a fallback
+   response is not sorted by `score`), and `fallback_used = true` whenever Freesound was queried (even with 0 hits).
+   Fallback tracks are **not stored** in v1 (not even when picked): `GET /tracks/{id}` and
    `POST /why` serve them live, and a `pick` event only records the event. Exception: `POST /tracks/{id}/stems` on one
```
