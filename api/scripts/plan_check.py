"""Live planner check (PLAN.md T4.1): real Gemini + plan_cache in the dev DB, no CLAP needed.

    cd api && uv run --env-file ../.env python scripts/plan_check.py [--fresh] [--all]

For each query: plan once (Gemini, or the cache), then again (must be a cache hit, < 50 ms). `--fresh` deletes the
queries' plan_cache rows first so Gemini is really called. `--all` adds the 20 eval queries (20+ Gemini calls: mind
free-tier rate limits).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_queries import EVAL_QUERIES  # noqa: E402

from app.core import db, gemini, planner  # noqa: E402
from app.core.settings import Settings  # noqa: E402

ACCEPTANCE = [
    ("sad trumpet around 90 bpm, no drums", []),
    ("just the drums, fast breakbeat", []),
    ("clean acapella in A minor", ["genre.soul"]),
]
CACHE_HIT_MS = 50.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="delete the queries' plan_cache rows first")
    ap.add_argument("--all", action="store_true", help="also plan the 20 eval queries")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    settings = Settings.from_env()
    pool = db.open_pool(settings)
    g = gemini.from_settings(settings)
    print(f"model {g.model}; degraded: {g.degraded_reason()}")
    queries = ACCEPTANCE + ([(t, c) for t, c in EVAL_QUERIES if t] if args.all else [])
    problems = 0
    try:
        if args.fresh:
            keys = [planner.cache_key(planner.normalize_text(t) or "", c) for t, c in queries]
            with pool.connection() as conn:
                n = conn.execute("delete from plan_cache where hash = any(%s)", (keys,)).rowcount
            print(f"deleted {n} plan_cache rows")
        for text, chip_ids in queries:
            norm = planner.normalize_text(text)
            chips = planner.resolve_chips(chip_ids, settings.vocab_path)
            timings = []
            outcomes = []
            for _ in range(2):
                t0 = time.perf_counter()
                outcomes.append(
                    planner.make_plan(norm, chips, chip_ids, pool=pool, gemini=g, vocab_path=settings.vocab_path)
                )
                timings.append((time.perf_counter() - t0) * 1000)
            first, second = outcomes
            ok = second.cached and timings[1] < CACHE_HIT_MS and second.plan == first.plan
            problems += not ok
            print(f"\n{'ok ' if ok else 'BAD'} {text!r} chips={chip_ids}")
            print(f"    1st {first.source:8} {timings[0]:7.0f} ms   2nd {second.source:8} {timings[1]:6.1f} ms")
            print(f"    {json.dumps(first.plan.model_dump(exclude_defaults=True), ensure_ascii=False)}")
    finally:
        pool.close()
    print(f"\n{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
