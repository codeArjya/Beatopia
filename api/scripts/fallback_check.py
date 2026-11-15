"""Live Freesound fallback check (PLAN.md T8.1), in process against the real DB, CLAP, Gemini and Freesound.

    cd api && uv run --env-file ../.env python scripts/fallback_check.py [--stems]

1. The 20 eval queries must NOT fall back (they're all well served by the library).
2. Out-of-library queries ("kazoo orchestra", sound effects) should fall back; every response is validated.
3. On "kazoo orchestra": GET /tracks/fs_* (live), POST /why twice (2nd from memory), a `pick` event, and no
   `tracks` row afterwards (fallback tracks aren't stored).
4. --stems: POST /tracks/fs_*/stems stores the minimal row + preview copy and queues a job; polls it for 4 min.
   This writes to the shared DB and bucket, and the production worker picks the job up.
Costs one Gemini planner call per query not yet in plan_cache (v2 keys), plus 1 /why note.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_queries import EVAL_QUERIES  # noqa: E402

from app.core.settings import REPO_ROOT, Settings  # noqa: E402
from app.main import create_app  # noqa: E402

EXPECT_FALLBACK = {"kazoo orchestra"}  # in EVAL_QUERIES on purpose ("nonsense")
OUT_QUERIES = ["kazoo orchestra", "bagpipes marching band", "didgeridoo drone", "dog barking", "rain on a tin roof"]
SCHEMA = json.loads((REPO_ROOT / "shared" / "schema" / "api.schema.json").read_text("utf-8"))


def check(body: object, name: str) -> None:
    jsonschema.validate(body, {"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]})


def total_ms(r: object) -> str:
    header = r.headers.get("server-timing", "")  # type: ignore[attr-defined]
    parts = dict(p.strip().split(";dur=") for p in header.split(",") if ";dur=" in p)
    return f"{float(parts.get('total', 0)):6.0f} ms (fs {float(parts.get('freesound', 0)):4.0f})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stems", action="store_true", help="also request stems on a fallback track (writes)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    settings = Settings.from_env()
    failures = 0

    with TestClient(create_app(settings)) as c:
        if c.app.state.freesound is None:  # type: ignore[attr-defined]
            print("FREESOUND_API_KEY is not set")
            return 1

        def search(text: str | None, chips: list[str]) -> dict:
            r = c.post("/search", json={"text": text, "chips": chips, "session_id": "fallback_check"})
            r.raise_for_status()
            body = r.json()
            check(body, "SearchResponse")
            n_fs = sum(x["track"]["source"] == "freesound" for x in body["results"])
            label = f"{text or ''} {' '.join(chips)}".strip()
            print(f"  {total_ms(r)}  fallback={body['fallback_used']!s:5} fs={n_fs} n={len(body['results'])}  {label}")
            return body

        print("eval queries (expected: no fallback, except the one marked nonsense)")
        false_alarms = [t for t, ch in EVAL_QUERIES if search(t, ch)["fallback_used"] and t not in EXPECT_FALLBACK]
        print(f"-> fallback on {len(false_alarms)}/{len(EVAL_QUERIES)} eval queries {false_alarms}")
        failures += bool(false_alarms)

        print("out-of-library queries (expected: fallback)")
        bodies = {q: search(q, []) for q in OUT_QUERIES}
        missed = [q for q, b in bodies.items() if not b["fallback_used"]]
        print(f"-> fallback on {len(OUT_QUERIES) - len(missed)}/{len(OUT_QUERIES)}; missed {missed}")
        failures += "kazoo orchestra" in missed

        kazoo = bodies["kazoo orchestra"]
        fs = next((x for x in kazoo["results"] if x["track"]["source"] == "freesound"), None)
        if fs is None:
            print("FAIL: no Freesound result for 'kazoo orchestra'")
            return 1
        t = fs["track"]
        print(f"first fallback result: {fs['window_id']} {t['title']!r} {t['license']} | {t['attribution']}")
        failures += not (t["attribution"] and t["license"])

        r = c.get(f"/tracks/{t['id']}")
        check(r.json(), "TrackDetail")
        print(f"GET /tracks/{t['id']}: {r.status_code}, {len(r.json()['windows'])} window, {total_ms(r)}")
        for i in (1, 2):
            r = c.post("/why", json={"window_id": fs["window_id"]})
            if r.status_code != 200:
                print(f"FAIL /why {r.status_code}: {r.text}")
                failures += 1
                break
            check(r.json(), "WhyResponse")
            note = r.json()["note"]
            print(f"POST /why #{i}: {total_ms(r)} {len(note.split())} words: {note}")

        r = c.post("/events", json={"session_id": "fallback_check", "window_id": fs["window_id"], "action": "pick"})
        pool = c.app.state.pool  # type: ignore[attr-defined]
        with pool.connection() as conn:
            stored = conn.execute("select 1 from tracks where id = %s", (t["id"],)).fetchone()
        print(f"pick event: {r.status_code}; tracks row after pick: {'yes' if stored else 'no'}")
        failures += r.status_code != 204 or (stored is not None and not args.stems)

        if args.stems:
            r = c.post(f"/tracks/{t['id']}/stems", json={"start_s": 0, "end_s": fs["end_s"]})
            print(f"POST /tracks/{t['id']}/stems: {r.status_code} {r.text[:200]} {total_ms(r)}")
            job_id = r.json().get("job_id") if r.status_code == 200 else None
            deadline = time.time() + 240
            while job_id and time.time() < deadline:
                job = c.get(f"/jobs/{job_id}").json()
                if job["status"] in ("done", "error"):
                    check(job, "Job")
                    stems = [s["stem"] for s in (job.get("output") or {}).get("stems", [])]
                    print(f"job {job_id}: {job['status']} {job.get('error') or ''} stems={stems}")
                    failures += job["status"] != "done"
                    break
                time.sleep(3)
            else:
                if job_id:
                    print(f"job {job_id} still not finished after 4 min (is the worker running?)")

    print("OK" if not failures else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
