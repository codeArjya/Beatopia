"""One-job-at-a-time worker. Claims commit before any download or model work."""

import json
import os
import time
from pathlib import Path

from common import db
from worker.jobs import claim, progress, terminate


def run_job(job: dict, root: Path) -> None:
    started = time.perf_counter()
    timings: dict = {}
    try:
        from worker.handlers import analyze_job, stems_job

        handler = {"stems": stems_job, "analyze": analyze_job}[job["kind"]]
        output = handler(job["input"], root, lambda value: progress(job["id"], value), timings)
        terminate(job["id"], output=output)
        status = "done"
    except Exception as error:
        import traceback

        timings["failure"] = {
            "type": type(error).__name__,
            "frames": [
                {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                for frame in traceback.extract_tb(error.__traceback__)
            ],
        }
        # Network/model exceptions may contain credentials, URLs or private metadata.
        message = str(error) if isinstance(error, ValueError) else "processing failed; inspect local checkpoints"
        terminate(job["id"], error=f"{type(error).__name__}: {message}"[:1000])
        status = "error"
    record = {
        "job_id": str(job["id"]),
        "kind": job["kind"],
        "status": status,
        "end_to_end_s": time.perf_counter() - started,
        "time": time.time(),
        **timings,
    }
    root.mkdir(parents=True, exist_ok=True)
    with (root / "worker.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(record, allow_nan=False) + "\n")
    print(json.dumps(record, allow_nan=False), flush=True)


def main() -> None:
    root = Path(os.environ.get("WORKER_DATA_DIR", "worker/data"))
    while True:
        try:
            job = claim()
        except db.psycopg.OperationalError:
            print('{"event":"claim_database_unavailable"}', flush=True)
            time.sleep(1)
            continue
        if job is not None:
            run_job(job, root)
        if os.environ.get("WORKER_ONCE") == "1":
            return
        if job is None:
            time.sleep(1)


if __name__ == "__main__":
    main()
