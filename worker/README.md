# worker/ (owner: **WS1**, Audio data & stems)

Polls `jobs` and runs `stems` (Demucs) and `analyze` (import analysis) jobs per CONTRACT §3.
Entrypoint `python -m worker.main` (WS2's container runs exactly this); config comes only from env.

```bash
cd worker && uv sync && cd .. && make dev-worker
```
