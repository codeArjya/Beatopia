"""Live /why check (PLAN.md T4.3): real DB + Gemini + ffmpeg on the dev bucket, no CLAP needed.

    cd api && uv run --env-file ../.env python scripts/why_check.py [--n 4]

Picks windows without a cached note (a mix window with a bpm, a stem window, a null-bpm window, then any), asks for
a note twice (the 2nd must come from the cache) and checks ≤ 45 words. One extra window runs with the excerpt
forced to fail (text-only P3b). Writes real rows to `notes`: they are the cache.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import db, excerpt, gemini, why  # noqa: E402
from app.core.settings import Settings  # noqa: E402
from app.core.timing import Timer, _current  # noqa: E402

PICK_SQL = """
select w.id from windows w join tracks t on t.id = w.track_id
where not exists (select 1 from notes n where n.window_id = w.id) and t.source <> 'import' and {cond}
order by md5(w.id) limit 1
"""
KINDS = [
    ("mix + bpm", "w.stem = 'mix' and t.bpm is not null and cardinality(t.beat_times) > 0"),
    ("stem", "w.stem <> 'mix'"),
    ("null bpm", "t.bpm is null"),
    ("any", "true"),
]


def timed(fn: object, *args: object) -> tuple[object, float, Timer]:
    timer = Timer()
    token = _current.set(timer)
    try:
        t0 = time.perf_counter()
        out = fn(*args)  # type: ignore[operator]
        return out, (time.perf_counter() - t0) * 1000, timer
    finally:
        _current.reset(token)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=len(KINDS), help="audio windows to check (max 4 kinds)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    settings = Settings.from_env()
    pool = db.open_pool(settings)
    g = gemini.from_settings(settings)
    print(f"model {g.model}; degraded: {g.degraded_reason()}")
    problems = 0
    try:
        picks: list[tuple[str, str]] = []
        with pool.connection() as conn:
            for kind, cond in [*KINDS[: args.n], ("text-only (forced)", "true")]:
                taken = [w for _, w in picks]
                row = conn.execute(PICK_SQL.format(cond=f"{cond} and not (w.id = any(%s))"), (taken,)).fetchone()
                if row:
                    picks.append((kind, row[0]))
                else:
                    print(f"(no uncached window for {kind})")

        real_cut = excerpt.cut_excerpt
        for kind, wid in picks:
            forced = kind.startswith("text-only")
            if forced:

                def broken(*_: object) -> bytes:
                    raise excerpt.ExcerptError("forced failure (why_check)")

                excerpt.cut_excerpt = broken
            try:
                first, ms1, t1 = timed(why.run_why, wid, pool, g)
            except Exception as exc:  # noqa: BLE001
                problems += 1
                print(f"\nBAD {kind:18} {wid}: {exc}")
                continue
            finally:
                excerpt.cut_excerpt = real_cut
            second, ms2, t2 = timed(why.run_why, wid, pool, g)
            words = len(first.note.split())  # type: ignore[attr-defined]
            src1, src2 = t1.fields.get("why_source"), t2.fields.get("why_source")
            ok = words <= why.NOTE_MAX_WORDS and src2 == "cache" and second.note == first.note  # type: ignore[attr-defined]
            if forced:
                ok = ok and src1 == "text"
            problems += not ok
            stages = " ".join(f"{k}={v:.0f}" for k, v in t1.stages.items())
            print(f"\n{'ok ' if ok else 'BAD'} {kind:18} {wid}")
            print(f"    1st {src1:6} {ms1:6.0f} ms ({stages}, {t1.fields.get('excerpt_kb', '-')} KB)")
            print(f"    2nd {src2:6} {ms2:6.0f} ms   {words} words")
            print(f"    {first.note}")  # type: ignore[attr-defined]
    finally:
        pool.close()
    print(f"\n{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
