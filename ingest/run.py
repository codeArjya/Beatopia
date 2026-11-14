"""Bounded resumable ingest: python -m ingest.run --source auto --limit 350."""

import argparse
import json
import os
import time
import traceback
from pathlib import Path

import httpx

from common import clap
from ingest.pipeline import fingerprint, process
from ingest.sources import Discovery, write_json


def emit(root: Path, event: str, **fields: object) -> None:
    line = json.dumps({"time": time.time(), "event": event, **fields}, sort_keys=True)
    print(line, flush=True)
    with (root / "ingest.log").open("a", encoding="utf-8") as log:
        log.write(line + "\n")


def failure_details(error: Exception) -> dict[str, object]:
    frames = traceback.extract_tb(error.__traceback__)
    frame = frames[-1] if frames else None
    return {
        "error_type": type(error).__name__,
        "location": f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" if frame else None,
        "http_status": error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["auto", "freesound", "jamendo", "fma"], default="auto")
    parser.add_argument("--limit", type=int, default=350)
    parser.add_argument("--data-dir", type=Path, default=Path("ingest/data"))
    parser.add_argument("--hero", type=int)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 400:
        parser.error("--limit must be between 1 and 400")
    if args.hero is not None:
        from ingest.heroes import main as heroes_main

        heroes_main(["--limit", str(args.hero), "--data-dir", str(args.data_dir)])
        return
    if args.source == "fma":
        parser.error("FMA ingest is not implemented")
    if clap.CLAP_MODEL == "laion/larger_clap_music":
        parser.error("Default checkpoint fails semantic acceptance; coordinate CLAP_MODEL/REVISION first")
    if clap.CLAP_REVISION == "main":
        parser.error("Set an immutable CLAP_REVISION before corpus ingest")
    root = args.data_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    # OS lock releases automatically after a crash. Never remove another process's lock file.
    with (root / "ingest.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(root, args.source, args.limit)


def run(root: Path, source: str, limit: int) -> None:
    identity_path = root / "fingerprint.json"
    identity = fingerprint()
    if identity_path.exists() and json.loads(identity_path.read_text()) != identity:
        raise ValueError("Run fingerprint differs; explicit corpus migration required")
    write_json(identity_path, identity)
    keys = {"freesound": os.environ.get("FREESOUND_API_KEY", ""), "jamendo": os.environ.get("JAMENDO_CLIENT_ID", "")}
    emit(root, "start", pid=os.getpid(), target=limit, fingerprint=identity)
    started = time.monotonic()
    capacity = min(400, limit + max(5, round(limit * 0.15)))
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        discovery = Discovery(root, client, keys)
        queue = []
        if source in {"auto", "jamendo"} and keys["jamendo"].strip():
            try:
                queue = discovery.discover("jamendo", min(150, limit) if source == "auto" else limit)
            except Exception as error:
                emit(root, "discovery_failure", source="jamendo", **failure_details(error))
        elif source in {"auto", "jamendo"}:
            emit(root, "fallback", reason="JAMENDO_CLIENT_ID absent", source="freesound")
        if len(queue) < capacity:
            try:
                queue += discovery.discover("freesound", capacity - len(queue))
            except Exception as error:
                emit(root, "discovery_failure", source="freesound", **failure_details(error))
                if not queue:
                    raise SystemExit(1) from None
        write_json(root / "queue.json", [item.metadata() for item in queue])
        emit(root, "queued", count=len(queue), target=limit)
        completed, failed = 0, 0
        for index, item in enumerate(queue):
            if completed >= limit:
                break
            track_start = time.monotonic()
            try:
                outcome = process(item, root, client)
                completed += 1
                emit(root, "track", id=item.id, outcome=outcome, seconds=time.monotonic() - track_start)
            except Exception as error:
                failed += 1
                emit(root, "failure", id=item.id, **failure_details(error), seconds=time.monotonic() - track_start)
            elapsed = time.monotonic() - started
            emit(
                root,
                "progress",
                completed=completed,
                failed=failed,
                attempted=index + 1,
                queued=len(queue),
                elapsed_s=elapsed,
                eta_s=elapsed / (index + 1) * min(len(queue) - index - 1, limit - completed),
            )
        emit(
            root,
            "finished",
            completed=completed,
            failed=failed,
            queued=len(queue),
            elapsed_s=time.monotonic() - started,
        )
        if failed or completed < limit:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
