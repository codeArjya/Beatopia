# ingest/ (owner: **WS1**, Audio data & stems)

Library ingest (Freesound, Jamendo, FMA) and the hero stem batch. `vocab.txt` is the tag vocabulary, shared with
`/chips` (WS2) and the chip tray (WS3): announce changes after H12.

```bash
cd ingest && uv sync
uv run --project ingest python -m ingest.run --source freesound --limit 20
```
Plan: `ingest/PLAN.md` (written in the WS1 kickoff). Handoff: `docs/handoff/WS1-data-stems.md`.
