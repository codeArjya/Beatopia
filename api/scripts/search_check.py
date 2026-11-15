"""Live /search check against the real DB + CLAP, in process (PLAN.md T3.2; reused after T4.x).

    cd api && uv run --env-file ../.env python scripts/search_check.py [--passes 2]

Needs the same CLAP_MODEL / CLAP_REVISION as ingest (proposal C8). Validates every response against the Pydantic model
and shared/schema, then prints p50/p95 of the server-side total (Server-Timing) and the fallback rate: a query
"needs the fallback" when fewer than 3 results score > 0.25 (CONTRACT §7.7).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # api/ (app) and api/scripts (eval_queries)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_queries import EVAL_QUERIES  # noqa: E402

from app.core.settings import REPO_ROOT, Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.api import SearchResponse  # noqa: E402
from common import clap  # noqa: E402

FALLBACK_SCORE = 0.25
FALLBACK_MIN_RESULTS = 3


def server_total_ms(header: str) -> float:
    parts = dict(p.strip().split(";dur=") for p in header.split(","))
    return float(parts["total"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=2, help="pass 1 embeds every query; later passes hit the LRU")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]  # Windows consoles

    schema = json.loads((REPO_ROOT / "shared" / "schema" / "api.schema.json").read_text("utf-8"))
    validator = {"$ref": "#/$defs/SearchResponse", "$defs": schema["$defs"]}
    print(f"CLAP {clap.CLAP_MODEL} @ {getattr(clap, 'CLAP_REVISION', 'main')}")

    t0 = time.perf_counter()
    with TestClient(create_app(Settings.from_env())) as c:
        print(f"startup (pool + CLAP warm) {time.perf_counter() - t0:.1f} s")
        for p in range(1, args.passes + 1):
            totals: list[float] = []
            fallbacks = 0
            for text, chips in EVAL_QUERIES:
                r = c.post("/search", json={"text": text, "chips": chips, "session_id": "search_check"})
                if r.status_code != 200:
                    print(f"FAIL {r.status_code} {text!r} {chips}: {r.text}")
                    return 1
                body = r.json()
                jsonschema.validate(body, validator)
                resp = SearchResponse.model_validate(body)
                totals.append(server_total_ms(r.headers["server-timing"]))
                good = sum(x.score > FALLBACK_SCORE for x in resp.results)
                fallbacks += good < FALLBACK_MIN_RESULTS
                if p == 1:
                    top = resp.results[0] if resp.results else None
                    label = f"{text or ''} {' '.join(chips)}".strip()
                    best = f"{top.score:.3f} {top.track.title[:28]} [{', '.join(top.tags[:3])}]" if top else "none"
                    print(f"  {totals[-1]:7.0f} ms  n={len(resp.results)} >0.25={good}  {label[:40]:40} -> {best}")
                    print(f"           {r.headers['server-timing']}")
            totals.sort()
            p95 = totals[min(len(totals) - 1, round(0.95 * (len(totals) - 1)))]
            print(
                f"pass {p}: p50 {statistics.median(totals):.0f} ms, p95 {p95:.0f} ms, max {totals[-1]:.0f} ms; "
                f"fallback needed {fallbacks}/{len(EVAL_QUERIES)} ({100 * fallbacks / len(EVAL_QUERIES):.0f}%)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
