"""Live rerank + notes check (PLAN.md T4.2): real DB + CLAP + Gemini, in process.

    cd api && uv run --env-file ../.env python scripts/rerank_check.py [query ...]

Each query runs twice. Run 1 should rerank (status "ok") and fill `why` on every result; run 2 should find the notes
cached (memo) and skip the rerank. Writes real rows to `notes` (that's the cache). Needs the CLAP env of proposal C8.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.settings import REPO_ROOT, Settings  # noqa: E402
from app.main import create_app  # noqa: E402

DEFAULT_QUERIES = ["dusty soul keys", "sad trumpet around 90 bpm, no drums", "clean jazzy guitar intro"]
PAUSE_S = 20.0  # free tier: only a few requests per minute (429 otherwise)


class Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, object]] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == "app.request":
            self.records.append(json.loads(record.getMessage()))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    queries = sys.argv[1:] or DEFAULT_QUERIES
    schema = json.loads((REPO_ROOT / "shared" / "schema" / "api.schema.json").read_text("utf-8"))
    validator = {"$ref": "#/$defs/SearchResponse", "$defs": schema["$defs"]}
    lines = Lines()
    problems = 0
    with TestClient(create_app(Settings.from_env())) as c:
        logging.getLogger("app.request").addHandler(lines)
        print(f"gemini {c.app.state.gemini.model}; degraded: {c.app.state.gemini.degraded_reason()}")  # type: ignore[attr-defined]
        for q in queries:
            for run in (1, 2):
                r = c.post("/search", json={"text": q, "session_id": "rerank_check"})
                body = r.json()
                log = lines.records[-1]
                if r.status_code != 200:
                    print(f"FAIL {r.status_code} {q!r}: {r.text}")
                    problems += 1
                    continue
                jsonschema.validate(body, validator)
                res = body["results"]
                with_why = sum(1 for x in res if x["why"])
                status = log.get("rerank")
                expect = "ok" if run == 1 else "skipped:memo"
                ok = with_why == len(res) and (status == expect or status in ("skipped:cached", "skipped:memo"))
                problems += not ok
                print(
                    f"\n{'ok ' if ok else 'BAD'} run {run} {q!r}: {len(res)} results, {with_why} with why, "
                    f"rerank={status} new_notes={log.get('new_notes')} plan={log.get('plan_source')} "
                    f"| total {log.get('ms')} ms, plan {log.get('plan_ms')}, rerank {log.get('rerank_ms')}"
                )
                if run == 1:
                    for x in res[:4]:
                        print(f"    {x['score']:.2f} {x['track']['title'][:30]:30} {x['tags'][:3]}  why: {x['why']}")
                time.sleep(PAUSE_S)
    print(f"\n{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
