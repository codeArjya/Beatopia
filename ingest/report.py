"""Read-only corpus audit. Technical playback checks are not listening approval."""

import argparse
import hashlib
import io
import json
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf
from psycopg.rows import dict_row

from common import analysis, db, storage
from common.ids import window_id
from ingest import density, heroes, pipeline
from ingest.sources import cc_license, write_json

STEMS = set(heroes.STEMS)


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot() -> dict:
    """Release the consistent read-only snapshot before any HTTP or decoding work."""
    with db.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        with conn.cursor(row_factory=dict_row, binary=True) as cursor:
            result = {"snapshot_at": datetime.now(UTC).isoformat()}
            for table, columns in (
                ("tracks", "*"),
                ("windows", "*"),
                ("stems", "*"),
                ("jobs", "id,kind,status,progress,error IS NOT NULL AS has_error"),
            ):
                # Table/column names are fixed literals, never command-line inputs.
                cursor.execute(f"SELECT {columns} FROM {table}")
                result[table] = [dict(row) for row in cursor.fetchall()]
    return result


def vector_array(value: object) -> np.ndarray:
    return np.asarray(value.to_numpy() if hasattr(value, "to_numpy") else value, dtype=np.float32)


def window_issues(w: dict, track: dict, vocab: set[str]) -> list[str]:
    problems = []
    v = vector_array(w["embedding"])
    if v.shape != (512,) or not np.isfinite(v).all() or not np.isclose(np.linalg.norm(v), 1, atol=1e-4):
        problems.append("embedding")
    numbers = [w[k] for k in ("start_s", "end_s", "rms", "density", "loopability")]
    if (
        not np.isfinite(numbers).all()
        or not 0 <= w["start_s"] < w["end_s"] <= track["duration_s"] + 0.001
        or not 0 <= w["density"] <= 1
        or not 0 <= w["loopability"] <= 1
        or w["rms"] < 10 ** (-45 / 20)
    ):
        problems.append("range_or_features")
    if w["stem"] not in STEMS | {"mix", "guitar", "piano"} or w["id"] != window_id(
        w["track_id"], w["stem"], w["start_s"]
    ):
        problems.append("id_or_stem")
    scores = w["tag_scores"]
    if (
        set(scores) != vocab
        or not set(w["tags"]) <= vocab
        or len(w["tags"]) != len(set(w["tags"]))
        or not np.isfinite(list(scores.values())).all()
        or any(abs(v) > 1.00001 for v in scores.values())
    ):
        problems.append("tags_or_scores")
    return problems


def compare_windows(expected: list[dict], vectors: np.ndarray, actual: list[dict]) -> None:
    indexed = {w["id"]: w for w in actual}
    if len(indexed) != len(actual) or set(indexed) != {w["id"] for w in expected}:
        raise ValueError("Window set mismatch")
    keys = ("start_s", "end_s", "rms", "density", "loopability")
    for w, vector in zip(expected, vectors, strict=True):
        row = indexed[w["id"]]
        if (
            row["tags"] != w["tags"]
            or row["tag_scores"] != w["tag_scores"]
            or not np.allclose([row[k] for k in keys], [w[k] for k in keys], atol=1e-5)
            or not np.allclose(vector_array(row["embedding"]), vector, atol=1e-6)
        ):
            raise ValueError("Window values mismatch")


def full_stems(track: dict, rows: list[dict]) -> bool:
    tid = track["id"]
    return all(
        any(
            r["stem"] == stem
            and r["range_start_s"] == 0
            and abs(r["range_end_s"] - track["duration_s"]) < 0.01
            and r["path"] == f"tracks/{tid}/stems/{stem}.mp3"
            and r["model"] == "htdemucs"
            for r in rows
        )
        for stem in STEMS
    )


def log_events(path: Path) -> list[dict]:
    """Ignore an incomplete final append, but expose it instead of hiding log damage."""
    events = []
    if path.exists():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                events.append({"event": "unreadable_log_line", "line": number})
                continue
            events.append(
                {
                    k: row[k]
                    for k in (
                        "time",
                        "event",
                        "id",
                        "error_type",
                        "location",
                        "http_status",
                        "completed",
                        "failed",
                        "target",
                        "eta_s",
                        "pid",
                    )
                    if k in row
                }
            )
    return events


def example(w: dict, tracks: dict[str, dict]) -> dict:
    t = tracks[w["track_id"]]
    return {
        **{k: w[k] for k in ("id", "track_id", "stem", "start_s", "end_s", "tags", "density", "rms")},
        **{k: t[k] for k in ("title", "artist", "license", "attribution", "source")},
        "top_scores": sorted(w["tag_scores"].items(), key=lambda item: (-item[1], item[0]))[:5],
        "listening": "unreviewed",
    }


def public_object(spec: dict, client: httpx.Client) -> dict:
    result = {k: spec[k] for k in ("path", "track_id", "duration_s")}
    try:
        response = client.get(storage.public_url(spec["path"]))
        result["http_status"] = response.status_code
        response.raise_for_status()
        content = response.content
        digest = hashlib.sha256(content).hexdigest()
        result.update(sha256=digest, bytes=len(content), hash_anchored=bool(spec.get("sha256")))
        if spec.get("sha256") and digest != spec["sha256"]:
            raise ValueError("Public hash mismatch")
        # Decode the actual public bytes, including all samples, not just a HEAD response.
        y, sr = sf.read(io.BytesIO(content), dtype="float32", always_2d=True)
        if (
            not len(y)
            or not np.isfinite(y).all()
            or sr != 44100
            or y.shape[1] != 2
            or abs(len(y) / sr - spec["duration_s"]) > 0.02
        ):
            raise ValueError("Public decode/format/duration mismatch")
        result.update(
            sample_rate=sr,
            channels=y.shape[1],
            decoded_duration_s=len(y) / sr,
            decoded_rms=float(np.sqrt(np.mean(y.astype(np.float64) ** 2))),
        )
        local = spec.get("local")
        if local and hashlib.sha256(Path(local).read_bytes()).hexdigest() != digest:
            raise ValueError("Local/public hash mismatch")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", "-i", "pipe:0"],
            input=content,
            capture_output=True,
            check=True,
            timeout=30,
        )
        streams = json.loads(probe.stdout)["streams"]
        result["streams"] = [
            {k: s[k] for k in ("codec_name", "codec_type", "sample_rate", "channels", "bit_rate") if k in s}
            for s in streams
        ]
        if len(streams) != 1 or streams[0].get("codec_name") != "mp3" or int(streams[0].get("bit_rate", 0)) != 192000:
            raise ValueError("Expected one 192k MP3 stream")
        result["verified"] = True
    except Exception as error:
        # Never serialize provider exception text (it may contain signed URLs/configuration).
        result.update(verified=False, error_type=type(error).__name__)
    return result


API_LICENSES = {"CC0", "CC-BY-3.0", "CC-BY-4.0"}  # WS2's Freesound fallback accepts CC0 and CC BY only


def is_api_materialized(t: dict, windows: list[dict], root: Path) -> bool:
    """A Freesound fallback track stored by the API before a stems request (CONTRACT §7.7, WS2
    `fallback.store_track`), not by ingest: no windows, no local ingest folder, and no analysis
    (bpm/key/beats). Ingest always writes windows and a manifest, so an ingested track never matches."""
    return (
        t["source"] == "freesound"
        and not windows
        and not (root / "tracks" / t["id"]).exists()
        and t.get("bpm") is None
        and t.get("key") is None
        and not t.get("beat_times")
    )


def api_materialized_issues(t: dict) -> list[str]:
    """What can be checked without an ingest manifest; the public mix is still decoded and probed."""
    issues = []
    if t["id"] != f"fs_{t.get('source_id')}":
        issues.append("id_source_mismatch")
    if t["audio_path"] != f"tracks/{t['id']}/mix.mp3":
        issues.append("audio_path")
    if t.get("license") not in API_LICENSES:
        issues.append("license")
    if not str(t.get("attribution") or "").strip():
        issues.append("attribution")
    if not (np.isfinite(t["duration_s"]) and t["duration_s"] > 0):
        issues.append("duration")
    return issues


def build_report(data: dict, root: Path, seed: int = 5) -> tuple[dict, list[dict]]:
    tracks = {t["id"]: t for t in data["tracks"]}
    windows, stems = defaultdict(list), defaultdict(list)
    for w in data["windows"]:
        windows[w["track_id"]].append(w)
    for s in data["stems"]:
        stems[s["track_id"]].append(s)
    api_tracks = {
        tid: t for tid, t in tracks.items() if t["source"] != "import" and is_api_materialized(t, windows[tid], root)
    }
    library = {tid: t for tid, t in tracks.items() if t["source"] != "import" and tid not in api_tracks}
    vocab = {tag for group in analysis._vocab().values() for tag in group}
    report = {
        "snapshot_at": data.get("snapshot_at", datetime.now(UTC).isoformat()),
        "seed": seed,
        "scope": "DB snapshot first; later objects/cache checks may overlap live publication",
        "counts": {
            "library_tracks": len(library),
            "api_materialized_tracks": len(api_tracks),
            "imports": len(tracks) - len(library) - len(api_tracks),
            "windows": len(data["windows"]),
            "stems": len(data["stems"]),
            "hero_flags": sum(t["is_hero"] for t in library.values()),
        },
        "source_license_counts": [
            dict(source=s, license=lic, count=n)
            for (s, lic), n in sorted(Counter((t["source"], t["license"]) for t in library.values()).items())
        ],
        "window_counts": dict(Counter(w["stem"] for w in data["windows"] if w["track_id"] in library)),
        "invalid_windows": [],
        "track_audit": [],
        "missing_stages": [],
    }
    all_windows = sorted([w for w in data["windows"] if w["track_id"] in library], key=lambda w: w["id"])
    report["random_windows"] = [
        example(w, tracks) for w in random.Random(seed).sample(all_windows, min(10, len(all_windows)))
    ]
    tag_examples = {}
    for tag in sorted(vocab):
        candidates = [w for w in all_windows if tag in w["tags"]]
        tag_examples[tag] = {
            "windows": len(candidates),
            "tracks": len({w["track_id"] for w in candidates}),
            "examples": [
                example(w, tracks)
                for w in sorted(candidates, key=lambda w: (-w["tag_scores"].get(tag, -1), w["id"]))[:3]
            ],
        }
    report["tags"] = tag_examples
    specs = {}
    for tid, t in sorted(library.items()):
        record = {
            "id": tid,
            "mix_verified": False,
            "hero_cache_verified": False,
            "density_verified": False,
            "issues": [],
        }
        for w in windows[tid]:
            problems = window_issues(w, t, vocab)
            if problems:
                report["invalid_windows"].append({"id": w["id"], "issues": problems})
                record["issues"].append("invalid_window")
        directory = root / "tracks" / tid
        path = t["audio_path"]
        specs[path] = dict(path=path, track_id=tid, duration_s=t["duration_s"])
        stage = "mix_cache_db_metadata"
        try:
            mix = read_json(directory / "manifest.json")
            vectors = pipeline.validate(mix, directory)
            if mix["fingerprint"] != pipeline.fingerprint():
                raise ValueError("Mix fingerprint mismatch")
            source = mix["source"]
            if cc_license(source["license_url"], jamendo=t["source"] == "jamendo") != t["license"]:
                raise ValueError("License mismatch")
            if (
                source["source"] != t["source"]
                or source["source_id"] != t["source_id"]
                or source["title"] != t["title"]
                or source["artist"] != t["artist"]
                or source["source_url"] != t["source_url"]
                or mix["attribution"] != t["attribution"]
                or not t["attribution"].strip()
                or abs(mix["duration_s"] - t["duration_s"]) > 0.01
                or path != f"tracks/{tid}/mix.mp3"
                or mix["key"] != t["key"]
                or (mix["bpm"] is None) != (t["bpm"] is None)
                or (mix["bpm"] is not None and not np.isclose(mix["bpm"], t["bpm"], atol=1e-4))
                or len(mix["beat_times"]) != len(t["beat_times"])
                or not np.allclose(mix["beat_times"], t["beat_times"], atol=1e-4)
            ):
                raise ValueError("Track metadata mismatch")
            expected_mix, migrated_later = density.snapshot_mix_windows(mix, directory, is_hero=t["is_hero"])
            compare_windows(expected_mix, vectors, [w for w in windows[tid] if w["stem"] == "mix"])
            record["density_migrated_after_snapshot"] = migrated_later
            record["mix_verified"] = True
            specs[path].update(sha256=mix["audio_sha256"], local=str(directory / "mix.mp3"))
            if t["is_hero"]:
                stage = "hero_cache_db_metadata"
                hdir = root / "heroes" / tid
                manifest = read_json(hdir / "manifest.json")
                identity = manifest["identity"]
                if identity["pipeline"] != mix["fingerprint"] or identity["mix_sha256"] != mix["audio_sha256"]:
                    raise ValueError("Hero identity mismatch")
                manifest, hv = heroes.cached(hdir, identity, mix)
                compare_windows(manifest["windows"], hv, [w for w in windows[tid] if w["stem"] in STEMS])
                if not full_stems(t, stems[tid]):
                    raise ValueError("Full hero stem rows incomplete")
                record["hero_cache_verified"] = True
                for stem in STEMS:
                    spath = f"tracks/{tid}/stems/{stem}.mp3"
                    specs[spath] = dict(
                        path=spath,
                        track_id=tid,
                        duration_s=t["duration_s"],
                        sha256=manifest["hashes"][stem],
                        local=str(hdir / f"{stem}.mp3"),
                    )
                stage = "hero_activity_density"
                record["density_audit"] = density.audit(root, mix, manifest, windows[tid])
                record["density_verified"] = record["density_audit"]["verified"]
        except Exception as error:
            record["issues"].append(f"{stage}:{type(error).__name__}")
        for s in stems[tid]:
            if (
                not np.isfinite([s["range_start_s"], s["range_end_s"]]).all()
                or not 0 <= s["range_start_s"] < s["range_end_s"] <= t["duration_s"] + 0.001
                or s["stem"] not in STEMS | {"guitar", "piano"}
            ):
                record["issues"].append("invalid_stem_range_or_name")
            if s["path"] not in specs:
                specs[s["path"]] = dict(path=s["path"], track_id=tid, duration_s=s["range_end_s"] - s["range_start_s"])
        report["track_audit"].append(record)
    # API-materialized fallback tracks: audited separately (no ingest manifest exists for them), never counted
    # toward the ingested-library targets. Their public mix and stems are still decoded and probed below.
    report["api_materialized_audit"] = []
    for tid, t in sorted(api_tracks.items()):
        issues = api_materialized_issues(t)
        specs[t["audio_path"]] = dict(path=t["audio_path"], track_id=tid, duration_s=t["duration_s"])
        for s in stems[tid]:
            if (
                not np.isfinite([s["range_start_s"], s["range_end_s"]]).all()
                or not 0 <= s["range_start_s"] < s["range_end_s"] <= t["duration_s"] + 0.001
                or s["stem"] not in STEMS | {"guitar", "piano"}
            ):
                issues.append("invalid_stem_range_or_name")
            specs.setdefault(
                s["path"], dict(path=s["path"], track_id=tid, duration_s=s["range_end_s"] - s["range_start_s"])
            )
        report["api_materialized_audit"].append({"id": tid, "stems": len(stems[tid]), "issues": issues})
    for name, queue_path, directory in (
        ("mix", root / "queue.json", root / "tracks"),
        ("hero", root / "heroes/queue.json", root / "heroes"),
    ):
        queue = read_json(queue_path) if queue_path.exists() else []
        for entry in queue:
            tid = (
                entry
                if isinstance(entry, str)
                else f"{'fs' if entry['source'] == 'freesound' else 'jam'}_{entry['source_id']}"
            )
            if tid in library and (name == "mix" or library[tid]["is_hero"]):
                continue
            folder = directory / tid
            report["missing_stages"].append(
                {
                    "id": tid,
                    "stage": name,
                    "published_in_snapshot": False,
                    "cached_files": sorted(p.name for p in folder.glob("*") if p.is_file()) if folder.exists() else [],
                }
            )
    for label, path in (("ingest", root / "ingest.log"), ("heroes", root / "heroes/heroes.log")):
        events = log_events(path)
        report[f"{label}_failures"] = [e for e in events if e["event"] in {"failure", "unreadable_log_line"}]
        report[f"{label}_last_progress"] = next((e for e in reversed(events) if e["event"] == "progress"), None)
    report["jobs"] = {
        "counts": dict(Counter(j["status"] for j in data["jobs"])),
        "errors": [{**j, "id": str(j["id"])} for j in data["jobs"] if j["status"] == "error"],
    }
    expected = set(read_json(Path(__file__).with_name("expected_errors.json"))["job_ids"])
    for job in report["jobs"]["errors"]:
        job["classification"] = (
            "intentional_session4_acceptance" if job["id"] in expected else "operational_unexplained"
        )
    return report, list(specs.values())


def finish_report(report: dict, objects: list[dict], reviews: list[dict] | None = None) -> None:
    report["objects"] = objects
    bad_tracks = {o["track_id"] for o in objects if not o["verified"]}
    verified = [r for r in report["track_audit"] if r["mix_verified"] and not r["issues"] and r["id"] not in bad_tracks]
    heroes_ok = [r["id"] for r in verified if r["hero_cache_verified"]]
    density_ok = [r for r in verified if r["hero_cache_verified"] and r.get("density_verified")]
    report["hero_density"] = {
        "verified_heroes": len(density_ok),
        "verified_windows": sum(r.get("density_audit", {}).get("windows", 0) for r in density_ok),
        "missing_hero_ids": [
            r["id"] for r in report["track_audit"] if r["hero_cache_verified"] and not r.get("density_verified")
        ],
        "method": density.METHOD,
        "scope": "All mix and stem windows of completed heroes in the read-only DB snapshot; independently decoded",
    }
    review_rows = []
    for review in reviews or []:
        tid, stem = review.get("track_id"), review.get("stem")
        matched = (
            tid in heroes_ok
            and stem in STEMS
            and review.get("status") == "identified_track_level_human_review"
            and bool(review.get("reviewer"))
            and bool(review.get("recorded_at"))
            and review.get("audio_path") == f"tracks/{tid}/stems/{stem}.mp3"
        )
        review_rows.append({**review, "matched_verified_hero": matched})
    report["listening_reviews"] = review_rows
    report["acceptance"] = {
        "technically_verified_library": len(verified),
        "technically_verified_heroes": len(heroes_ok),
        "verified_hero_ids": heroes_ok,
        "library_300_500": 300 <= len(verified) <= 500,
        "heroes_80": len(heroes_ok) >= 80,
        "hero_shortfall": max(0, 80 - len(heroes_ok)),
        "all_completed_hero_density": bool(heroes_ok)
        and len(density_ok) == report.get("counts", {}).get("hero_flags", len(heroes_ok)),
        "audibly_verified_prominent_timbres": 0,
        "human_reviewed_hero_tracks": len({r["track_id"] for r in review_rows if r["matched_verified_hero"]}),
        "prominent_timbres_30": "unverified",
        "listening": (
            "See identified human track-level reviews; exact-window/formal prominence judgments remain incomplete"
            if any(r["matched_verified_hero"] for r in review_rows)
            else "unreviewed; numerical tags and decoded audio do not establish prominent timbres"
        ),
        "full_quality_gate": "open",
    }
    report["finished_at"] = datetime.now(UTC).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("ingest/data"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=5)
    args = parser.parse_args()
    started = time.monotonic()
    report, specs = build_report(snapshot(), args.data_dir, args.seed)
    with httpx.Client(timeout=60, follow_redirects=True) as client, ThreadPoolExecutor(max_workers=4) as pool:
        objects = []
        for result in pool.map(lambda spec: public_object(spec, client), specs):
            objects.append(result)
            if len(objects) % 25 == 0:
                print(f"Audited public objects {len(objects)}/{len(specs)}", file=sys.stderr, flush=True)
    review_path = Path(__file__).with_name("listening-session5.json")
    finish_report(report, objects, [read_json(review_path)] if review_path.exists() else [])
    report["elapsed_s"] = time.monotonic() - started
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, indent=2, allow_nan=False))
    if (
        report["invalid_windows"]
        or any(r["issues"] for r in report["track_audit"])
        or any(r["issues"] for r in report.get("api_materialized_audit", []))
        or any(not o["verified"] for o in objects)
        or any(j["classification"] == "operational_unexplained" for j in report["jobs"]["errors"])
    ):
        raise SystemExit(1)
    # A target shortfall stays machine-visible even when there is no corrupt object.
    if (
        not report["acceptance"]["library_300_500"]
        or not report["acceptance"]["heroes_80"]
        or not report["acceptance"]["all_completed_hero_density"]
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"stage": "report", "error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
