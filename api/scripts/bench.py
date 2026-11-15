"""T6.3 latency bench: run the 20 eval queries against a live API and print p50/p95 per stage.

    uv run --project api python api/scripts/bench.py --url https://45-77-216-35.sslip.io
    uv run --project api python api/scripts/bench.py --url http://127.0.0.1:8000 --passes 2 --pause 3

Stage timings come from the `Server-Timing` header (plan, embed, sql, score, rerank, total); `client` is the wall
time seen from here (adds network + TLS). Pass 1 is "as cold as the caches are" (plan_cache / notes rows from earlier
runs still hit); later passes show the warm path. `--bust` appends a per-run nonce to every text query so the planner,
the plan cache and the rerank memo all miss (costs 2 Gemini calls per text query).
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_queries import EVAL_QUERIES  # noqa: E402

STAGES = ("plan", "embed", "sql", "score", "rerank", "total", "client")
TARGET_P50_MS = 3000.0


def parse_server_timing(header: str) -> dict[str, float]:
    """`plan;dur=12.3, sql;dur=4.0` → {"plan": 12.3, "sql": 4.0}. Unknown params and malformed parts are skipped."""
    out: dict[str, float] = {}
    for part in header.split(","):
        name, *params = (p.strip() for p in part.split(";"))
        for param in params:
            key, _, value = param.partition("=")
            if name and key == "dur":
                try:
                    out[name] = out.get(name, 0.0) + float(value)
                except ValueError:
                    pass
    return out


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100); fine for 20 samples."""
    ordered = sorted(values)
    rank = max(1, round(q / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def run_pass(client: httpx.Client, url: str, session_id: str, nonce: str | None, pause: float) -> list[dict]:
    rows: list[dict] = []
    for i, (text, chips) in enumerate(EVAL_QUERIES):
        body: dict = {"chips": chips, "limit": 8, "session_id": session_id}
        if text:
            body["text"] = f"{text} {nonce}" if nonce else text
        t = time.perf_counter()
        r = client.post(f"{url}/search", json=body)
        client_ms = (time.perf_counter() - t) * 1000
        stages = parse_server_timing(r.headers.get("server-timing", ""))
        stages["client"] = client_ms
        ok = r.status_code == 200
        data = r.json() if ok else {}
        rows.append(
            {
                "q": text or "+".join(chips),
                "status": r.status_code,
                "n": len(data.get("results", [])),
                "why": sum(1 for x in data.get("results", []) if x.get("why")),
                "fallback": data.get("fallback_used", False),
                **stages,
            }
        )
        if pause and i < len(EVAL_QUERIES) - 1:
            time.sleep(pause)
    return rows


def report(rows: list[dict], label: str) -> float:
    print(f"\n== {label}: {len(rows)} queries")
    print(f"{'query':40} {'st':>3} {'n':>2} {'why':>3} " + " ".join(f"{s:>7}" for s in STAGES))
    for row in rows:
        cells = " ".join(f"{row[s]:7.0f}" if s in row else f"{'-':>7}" for s in STAGES)
        print(f"{row['q'][:40]:40} {row['status']:>3} {row['n']:>2} {row['why']:>3} {cells}")
    print(f"{'p50':>51} " + " ".join(_pct(rows, s, 50) for s in STAGES))
    print(f"{'p95':>51} " + " ".join(_pct(rows, s, 95) for s in STAGES))
    totals = [r["total"] for r in rows if "total" in r]
    p50 = percentile(totals, 50) if totals else float("nan")
    errors = [r for r in rows if r["status"] != 200]
    stage_p50 = {s: percentile([r[s] for r in rows if s in r], 50) for s in STAGES[:5] if any(s in r for r in rows)}
    slowest = max(stage_p50, key=stage_p50.get) if stage_p50 else "-"
    verdict = "OK" if p50 < TARGET_P50_MS else "OVER"
    print(
        f"server total p50 {p50:.0f} ms ({verdict} vs {TARGET_P50_MS:.0f} ms target); slowest stage by p50: "
        f"{slowest} ({stage_p50.get(slowest, 0):.0f} ms); errors {len(errors)}; "
        f"fallback {sum(r['fallback'] for r in rows)}"
    )
    return p50


def _pct(rows: list[dict], stage: str, q: float) -> str:
    values = [r[stage] for r in rows if stage in r]
    return f"{percentile(values, q):7.0f}" if values else f"{'-':>7}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="API base URL, e.g. https://45-77-216-35.sslip.io")
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between queries (Gemini rate limits)")
    ap.add_argument("--bust", action="store_true", help="append a nonce to text queries so every cache misses")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    url = args.url.rstrip("/")
    nonce = f"#{uuid.uuid4().hex[:6]}" if args.bust else None
    session_id = f"bench-{uuid.uuid4()}"
    with httpx.Client(timeout=args.timeout, headers={"User-Agent": "beatopia-bench"}) as client:
        health = client.get(f"{url}/health")
        print(f"{url}/health → {health.status_code} {health.text.strip()}")
        p50s = [
            report(run_pass(client, url, session_id, nonce, args.pause), f"pass {p + 1}") for p in range(args.passes)
        ]
    return 0 if p50s and p50s[0] < TARGET_P50_MS else 1


if __name__ == "__main__":
    raise SystemExit(main())
