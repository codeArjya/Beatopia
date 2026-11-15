"""Resumable hero mix-density migration; preserve audio, vectors and original identities."""

import argparse
import copy
import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np

METHOD = "spectral-flatness+four-stem-rms-above-minus30dbfs-v1"


def sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def mix_input(mix: dict) -> str:
    original = copy.deepcopy(mix)
    original.pop("stem_activity_density", None)
    for w in original["windows"]:
        w.pop("density", None)
    return sha(original)


def receipt_path(directory: Path) -> Path:
    return directory / "stem-activity-density.json"


def check_receipt(receipt: dict, mix: dict) -> None:
    if (
        receipt["method"] != METHOD
        or receipt["track_id"] != mix["id"]
        or receipt["mix_input_sha256"] != mix_input(mix)
        or receipt["mix_audio_sha256"] != mix["audio_sha256"]
    ):
        raise ValueError("Density receipt input mismatch")
    values = receipt["densities"]
    if not values or any(not np.isfinite(v) or not 0 <= v <= 1 for v in values.values()):
        raise ValueError("Invalid measured densities")
    mix_ids = {w["id"] for w in mix["windows"]}
    if {wid for wid in values if wid.split(":")[1] == "mix"} != mix_ids:
        raise ValueError("Density receipt mix windows mismatch")


def validate_mix(mix: dict, directory: Path) -> None:
    """Called by the ordinary ingest validator: a resumed mix keeps its migrated values."""
    marker = mix.get("stem_activity_density")
    if marker is None:
        return
    receipt = json.loads(receipt_path(directory).read_text(encoding="utf-8"))
    check_receipt(receipt, mix)
    if marker != {"method": METHOD, "receipt_sha256": sha(receipt)} or any(
        not np.isclose(w["density"], receipt["densities"][w["id"]], atol=1e-7, rtol=0) for w in mix["windows"]
    ):
        raise ValueError("Migrated mix density mismatch")


def snapshot_mix_windows(mix: dict, directory: Path, *, is_hero: bool) -> tuple[list[dict], bool]:
    """A nonhero DB snapshot predates any later hero-density migration of its cache."""
    if is_hero or "stem_activity_density" not in mix:
        return mix["windows"], False
    validate_mix(mix, directory)
    receipt = json.loads(receipt_path(directory).read_text(encoding="utf-8"))
    previous = receipt["previous_mix_densities"]
    if set(previous) != {w["id"] for w in mix["windows"]} or any(
        not np.isfinite(v) or not 0 <= v <= 1 for v in previous.values()
    ):
        raise ValueError("Pre-migration density snapshot evidence missing or invalid")
    return [{**w, "density": previous[w["id"]]} for w in mix["windows"]], True


def audit(root: Path, mix: dict, hero: dict, rows: list[dict]) -> dict:
    """Re-decode all input bytes with the canonical feature decoder; never trust receipt values."""

    from ingest.heroes import digest
    from ingest.separation import STEMS, stereo

    tid = mix["id"]
    directory, hdir = root / "tracks" / tid, root / "heroes" / tid
    if "stem_activity_density" not in mix:
        return {"verified": False, "reason": "not_migrated", "windows": len(rows)}
    validate_mix(mix, directory)
    receipt = json.loads(receipt_path(directory).read_text(encoding="utf-8"))
    if receipt["hero_manifest_sha256"] != digest(hdir / "manifest.json") or receipt["stem_hashes"] != hero["hashes"]:
        raise ValueError("Density receipt stem identity mismatch")
    audio = {}
    for name in ("mix", *STEMS):
        path = directory / "mix.mp3" if name == "mix" else hdir / f"{name}.mp3"
        audio[name] = stereo(path)
    measured = measure(mix, hero, audio.pop("mix"), audio)
    actual = {w["id"]: w["density"] for w in rows}
    if len(actual) != len(rows) or set(actual) != set(measured) or set(actual) != set(receipt["densities"]):
        raise ValueError("Density audit full window set mismatch")
    if not np.isfinite(list(actual.values())).all():
        raise ValueError("Density audit nonfinite DB value")
    delta = max(abs(actual[k] - value) for k, value in measured.items())
    receipt_delta = max(abs(receipt["densities"][k] - value) for k, value in measured.items())
    if delta > 1e-5 or receipt_delta > 1e-5:
        raise ValueError("Density audit measurement mismatch")
    return {"verified": True, "windows": len(actual), "max_db_delta": delta, "max_receipt_delta": receipt_delta}


def measure(mix: dict, hero: dict, mix_audio: np.ndarray, arrays: dict[str, np.ndarray]) -> dict:
    from ingest.heroes import activity_density
    from ingest.separation import SR, STEMS

    if (
        set(arrays) != set(STEMS)
        or any(y.shape != mix_audio.shape or not np.isfinite(y).all() for y in arrays.values())
        or mix_audio.ndim != 2
        or mix_audio.shape[1] != 2
        or not np.isfinite(mix_audio).all()
    ):
        raise ValueError("Density requires aligned finite stereo mix and four stems")
    if abs(len(mix_audio) / SR - mix["duration_s"]) > 0.01:
        raise ValueError("Density audio coverage mismatch")
    measured = {}
    for stem, windows in (("mix", mix["windows"]), (None, hero["windows"])):
        for w in windows:
            name = stem or w["stem"]
            a, b = round(w["start_s"] * SR), round(w["end_s"] * SR)
            if not 0 <= a < b <= len(mix_audio) or any(
                w["start_s"] < p["processed_end_s"] < w["end_s"] for p in mix["offsets"]
            ):
                raise ValueError("Density window outside audio or across excerpt join")
            value = activity_density(mix_audio if name == "mix" else arrays[name], arrays, a, b)
            if w["id"] in measured:
                raise ValueError("Duplicate density window")
            if name != "mix" and not np.isclose(w["density"], value, atol=1e-5, rtol=0):
                raise ValueError("Existing stem activity density differs from decoded measurement")
            measured[w["id"]] = value
    return measured


def prepare(root: Path, tid: str) -> tuple[dict, dict, np.ndarray, dict, np.ndarray]:
    from ingest import heroes, pipeline
    from ingest.separation import STEMS, stereo
    from ingest.sources import write_json

    directory, hdir = root / "tracks" / tid, root / "heroes" / tid
    mix, path = heroes.load_mix(root, tid)
    vectors = pipeline.validate(mix, directory)
    hero = json.loads((hdir / "manifest.json").read_text(encoding="utf-8"))
    identity = hero["identity"]
    if identity["mix_sha256"] != mix["audio_sha256"] or identity["pipeline"] != mix["fingerprint"]:
        raise ValueError("Density hero identity mismatch")
    hero, hv = heroes.cached(hdir, identity, mix)
    anchors = {
        "method": METHOD,
        "track_id": tid,
        "mix_input_sha256": mix_input(mix),
        "mix_audio_sha256": mix["audio_sha256"],
        "hero_manifest_sha256": heroes.digest(hdir / "manifest.json"),
        "stem_hashes": hero["hashes"],
    }
    path_receipt = receipt_path(directory)
    if path_receipt.exists():
        receipt = json.loads(path_receipt.read_text(encoding="utf-8"))
        check_receipt(receipt, mix)
        if any(receipt[k] != v for k, v in anchors.items()):
            raise ValueError("Density receipt hero inputs changed; investigate before migration")
    else:
        arrays = {s: stereo(hdir / f"{s}.mp3") for s in STEMS}
        receipt = {
            **anchors,
            "previous_mix_densities": {w["id"]: w["density"] for w in mix["windows"]},
            "densities": measure(mix, hero, stereo(path), arrays),
        }
        # Write-ahead receipt survives either DB rollback or interruption before manifest replacement.
        write_json(path_receipt, receipt)
    if set(receipt["densities"]) != {w["id"] for w in mix["windows"] + hero["windows"]}:
        raise ValueError("Density receipt full window set mismatch")
    return mix, hero, vectors, receipt, hv


def apply(root: Path, tid: str) -> dict:
    from psycopg.rows import dict_row

    from common import db
    from ingest import report
    from ingest.sources import write_json

    mix, hero, vectors, receipt, hv = prepare(root, tid)
    directory = root / "tracks" / tid
    expected = [{**w, "stem": "mix"} for w in mix["windows"]] + hero["windows"]
    changed = 0
    with db.connect() as conn:
        # The session pooler's extra_float_digits=0 rounds float4 text to six significant digits.
        # Binary reads preserve stored float32 values and keep the strict verification tolerance.
        with conn.cursor(row_factory=dict_row, binary=True) as cursor:
            cursor.execute("SELECT * FROM tracks WHERE id=%s FOR UPDATE", (tid,))
            track = cursor.fetchone()
            if not track or not track["is_hero"] or track["source"] == "import":
                raise ValueError("Density requires a completed library hero")
            if abs(track["duration_s"] - mix["duration_s"]) > 0.01 or track["audio_path"] != f"tracks/{tid}/mix.mp3":
                raise ValueError("Density DB mix coverage mismatch")
            cursor.execute("SELECT * FROM stems WHERE track_id=%s", (tid,))
            if not report.full_stems(track, list(cursor.fetchall())):
                raise ValueError("Density requires four full hero stem rows")
            cursor.execute("SELECT * FROM windows WHERE track_id=%s FOR UPDATE", (tid,))
            rows = list(cursor.fetchall())
            # Check every pre-existing field/vector; density is the only permitted DB change.
            original = {w["id"]: w for w in expected}
            if any(w["track_id"] != tid or w["stem"] != original.get(w["id"], {}).get("stem") for w in rows):
                raise ValueError("Density DB track/stem mismatch")
            comparison = [{**w, "density": original.get(w["id"], w)["density"]} for w in rows]
            report.compare_windows(expected, np.concatenate((vectors, hv)), comparison)
            for row in rows:
                value = receipt["densities"][row["id"]]
                if not np.isclose(row["density"], value, atol=1e-7, rtol=0):
                    cursor.execute("UPDATE windows SET density=%s WHERE id=%s", (value, row["id"]))
                    changed += 1
    # Commit first. A crash here is visible as cache/DB mismatch and repaired using the same receipt.
    updated = copy.deepcopy(mix)
    for w in updated["windows"]:
        w["density"] = receipt["densities"][w["id"]]
    updated["stem_activity_density"] = {"method": METHOD, "receipt_sha256": sha(receipt)}
    if updated != mix:
        write_json(directory / "manifest.json", updated)
    validate_mix(updated, directory)
    with db.connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        actual = dict(conn.execute("SELECT id,density FROM windows WHERE track_id=%s", (tid,), binary=True).fetchall())
    if set(actual) != set(receipt["densities"]) or any(
        not np.isclose(actual[k], v, atol=1e-7, rtol=0) for k, v in receipt["densities"].items()
    ):
        raise ValueError("Post-migration density verification failed")
    return {"id": tid, "windows": len(actual), "mix_windows": len(mix["windows"]), "updated_rows": changed}


@contextmanager
def file_lock(path: Path, *, create: bool = True) -> Iterator[None]:
    """Separate migration lock; probing the producer lock never writes to it."""
    with path.open("a+b" if create else "r+b") as lock:
        if create and path.stat().st_size == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def producer_running(root: Path) -> bool:
    path = root / "heroes/heroes.lock"
    if not path.exists():
        return False
    # Check access separately; an open failure must propagate instead of looking like lock contention.
    with path.open("r+b"):
        pass
    try:
        with file_lock(path, create=False):
            return False
    except OSError as error:
        # Access/permission errors are not evidence that a producer is alive.
        if error.errno not in {11, 13, 36}:
            raise
        return True


def sweep(root: Path) -> dict:
    from common import db
    from ingest.run import failure_details

    with db.connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        ids = [r[0] for r in conn.execute("SELECT id FROM tracks WHERE is_hero AND source<>'import' ORDER BY id")]
    rows, failures = [], []
    for tid in ids:
        try:
            rows.append(apply(root, tid))
            print(json.dumps({"event": "density", **rows[-1]}), flush=True)
        except Exception as error:
            failures.append({"id": tid, **failure_details(error), "message": str(error)[:160]})
            print(json.dumps({"event": "density_failure", **failures[-1]}), flush=True)
    return {
        "time": time.time(),
        "pid": os.getpid(),
        "heroes_in_snapshot": len(ids),
        "verified_heroes": len(rows),
        "verified_windows": sum(r["windows"] for r in rows),
        "updated_rows": sum(r["updated_rows"] for r in rows),
        "tracks": rows,
        "failures": failures,
    }


def main() -> None:
    from ingest.sources import write_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("ingest/data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--follow", action="store_true", help="Sweep until the original hero producer releases its lock"
    )
    parser.add_argument("--poll-seconds", type=float, default=30)
    args = parser.parse_args()
    if not np.isfinite(args.poll_seconds) or not 1 <= args.poll_seconds <= 60:
        parser.error("--poll-seconds must be 1..60")
    root = args.data_dir.resolve()
    with file_lock(root / "density.lock"):
        while True:
            # Check before snapshot so producer shutdown is followed by one final complete sweep.
            running = producer_running(root) if args.follow else None
            started = time.monotonic()
            result = {**sweep(root), "producer_running_before_snapshot": running, "follow": args.follow}
            result["elapsed_s"] = time.monotonic() - started
            write_json(args.output, result)
            print(
                json.dumps({"event": "density_sweep", **{k: v for k, v in result.items() if k != "tracks"}}), flush=True
            )
            if result["failures"]:
                raise SystemExit(1)
            if not args.follow or not running:
                break
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
