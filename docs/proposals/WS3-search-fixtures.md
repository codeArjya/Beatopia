# Proposal WS3-search-fixtures: empty + fallback search fixtures; `window_id` is opaque

**Author:** WS3. **Status:** proposed. **Model or schema change:** none.

## Why
`search.json` is the only search fixture. It has 8 results, `fallback_used: false`, and every result has a bpm and an
artist. So fixture mode (the offline backup demo) can never show the "No matches, try fewer chips" state, the
"Expanded to Freesound" banner, or cards with missing BPM, key or artist. Those are exactly the states that break when
we go live at H12. Separately, several fixture `window_id`s don't follow `{track}:{stem}:{start_ms}` (for example
`fma_000123:mix:0` has `start_s: 2.667`). A client that parses the id would compute the wrong preview time.

## The change

### New file `shared/fixtures/search_empty.json`
```json
{
  "query_id": "q_e0e0e0e0",
  "plan": {
    "clap_text": "solo theremin over polka accordion, 200 bpm",
    "must_tags": ["theremin", "polka"],
    "exclude_tags": [],
    "bpm_range": [195.0, 205.0],
    "key": null,
    "stems_wanted": [],
    "prefer_sparse": false
  },
  "results": [],
  "fallback_used": true
}
```
(`fallback_used: true` with 0 results is the realistic worst case: the Freesound fallback ran and found nothing.)

### New file `shared/fixtures/search_fallback.json`
One weak library hit plus two Freesound fallback results with the nullable fields set to null:
```json
{
  "query_id": "q_fb5d1c00",
  "plan": {
    "clap_text": "lonely harmonica, sparse, dusty",
    "must_tags": ["harmonica"],
    "exclude_tags": [],
    "bpm_range": null,
    "key": null,
    "stems_wanted": [],
    "prefer_sparse": true
  },
  "results": [
    {
      "window_id": "fma_000123:mix:13333",
      "track": {
        "id": "fma_000123",
        "title": "Velvet Static",
        "artist": "The Quiet Arcade",
        "source": "fma",
        "source_url": "https://example.com/fixtures/fma/000123",
        "license": "CC-BY-4.0",
        "attribution": "\"Velvet Static\" by The Quiet Arcade, licensed under CC BY 4.0",
        "duration_s": 16.0,
        "bpm": 90.0,
        "key": "C major",
        "is_hero": false
      },
      "stem": "mix",
      "audio_url": "/fixtures/audio/mix.wav",
      "start_s": 13.333,
      "end_s": 16.0,
      "bars": 1,
      "tags": ["piano", "jazz", "bittersweet"],
      "score": 0.31,
      "why": null
    },
    {
      "window_id": "fs_733104:mix:0",
      "track": {
        "id": "fs_733104",
        "title": "harmonica_blues_riff_take3_FINAL_master_v2 (very long freesound title for truncation tests)",
        "artist": null,
        "source": "freesound",
        "source_url": "https://example.com/fixtures/freesound/733104",
        "license": "CC0",
        "attribution": "",
        "duration_s": 12.4,
        "bpm": null,
        "key": null,
        "is_hero": false
      },
      "stem": "mix",
      "audio_url": "/fixtures/audio/mix.wav",
      "start_s": 0.0,
      "end_s": 5.333,
      "bars": 2,
      "tags": [],
      "score": 0.22,
      "why": null
    },
    {
      "window_id": "fs_733190:mix:0",
      "track": {
        "id": "fs_733190",
        "title": "Harmonica sustain",
        "artist": "fixture_user",
        "source": "freesound",
        "source_url": "https://example.com/fixtures/freesound/733190",
        "license": "CC-BY-4.0",
        "attribution": "\"Harmonica sustain\" by fixture_user (Freesound), licensed under CC BY 4.0",
        "duration_s": 4.1,
        "bpm": null,
        "key": "E minor",
        "is_hero": false
      },
      "stem": "mix",
      "audio_url": "/fixtures/audio/mix.wav",
      "start_s": 0.0,
      "end_s": 2.667,
      "bars": 1,
      "tags": ["harmonica"],
      "score": 0.19,
      "why": null
    }
  ],
  "fallback_used": true
}
```
All audio points at the existing `/fixtures/audio/mix.wav`, so `make fixture-audio` doesn't change. The window ids
here follow `{track}:{stem}:{round(start_s*1000)}` as `common.ids.window_id` builds them.

### `scripts/check_fixtures.py`
Without these two entries, `make check-fixtures` reports the new files as "no model mapping":
```diff
 EXPECTED = {
     "chips": "ChipsResponse",
     "search": "SearchResponse",
+    "search_empty": "SearchResponse",
+    "search_fallback": "SearchResponse",
     "track_detail": "TrackDetail",
```

### `docs/CONTRACT.md`
§2, the window id row (clarification, no format change):
```diff
-| Window id | `{track_id}:{stem}:{start_ms}` | `fs_482913:mix:15000` |
+| Window id | `{track_id}:{stem}:{start_ms}`; **opaque to clients**: always read `start_s`/`end_s`, never parse the id | `fs_482913:mix:15000` |
```
§9, the fixture list:
```diff
-One JSON file per response type, valid against the generated schema: `chips.json`, `search.json` (8 results),
+One JSON file per response type, valid against the generated schema: `chips.json`, `search.json` (8 results),
+`search_empty.json` (0 results, `fallback_used`), `search_fallback.json` (3 low-score results incl. Freesound,
+null bpm/key/artist),
 `track_detail.json`, `stems_ready.json`, `stems_queued.json`, `job_running.json`, `job_done_stems.json`,
```

### Not changed on purpose
The existing ids in `search.json`, `track_detail.json` and `why.json` stay as they are, even though some don't match
`start_s`. `api/tests/test_stubs.py` and `web/lib/api/client.test.ts` already depend on them (for example
`fs_482913:mix:5000`). Renaming them would churn tests in two streams for no runtime benefit once ids are
declared opaque.

## Effect on other streams
- **WS1:** none. `common.ids.window_id` already produces well-formed ids for real data.
- **WS2:** none required. Optionally, the `/search` stub could return `search_empty` or `search_fallback` for a magic
  query (for example text `"__empty__"`) to test the live UI. That's WS2's call. WS2 must not parse `window_id`
  (it doesn't today; `/why` looks the id up in `notes`/`windows`).
- **WS3:** owns the fixture-mode selection. `web/lib/api/client.ts` will import both files and serve them in fixture
  mode behind a dev-only `?fixture=empty|fallback` URL param, with Vitest coverage. The default fixture behavior
  doesn't change.
- **WS4:** none. It must not parse `window_id` either (it uses `start`/`end` from the editor URL).

## Can it wait until the next gate?
**Yes.** It's additive and nobody is blocked. Until it lands, WS3's tests build these variants in memory from
`search.json`, which covers the H8 gate. It should land before **H12** (go-live), so the offline backup demo and the
live-data fixes have checked-in fixtures for empty results, the fallback banner and missing fields.
