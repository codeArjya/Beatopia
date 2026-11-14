"""Resumable hero ranking, benchmarks and verified publication. Separate from the ingest lock."""

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf
from psycopg.types.json import Jsonb

from common import analysis, clap, db, storage
from common.ids import window_id
from ingest.pipeline import fingerprint, validate
from ingest.run import failure_details
from ingest.separation import SR, STEMS, Engine, encode, stereo
from ingest.sources import write_json

# Exact existing vocabulary strings. These are tag-evidence candidates, not listening verdicts.
TIMBRES = {
    "trumpet",
    "horns",
    "trombone",
    "saxophone",
    "strings",
    "violin",
    "cello",
    "harp",
    "piano",
    "rhodes",
    "wurlitzer",
    "organ",
    "clavinet",
    "harpsichord",
    "mellotron",
}


def emit(root: Path, event: str, **fields: object) -> None:
    line = json.dumps({"time": time.time(), "event": event, **fields}, sort_keys=True)
    print(line, flush=True)
    with (root / "heroes.log").open("a", encoding="utf-8") as log:
        log.write(line + "\n")


def ranked(rows: list[dict], limit: int) -> tuple[list[dict], dict]:
    vocab = {tag for group in analysis._vocab().values() for tag in group}
    candidates = []
    for row in rows:
        tags = set(row["tags"]) & vocab
        candidates.append(
            {
                **row,
                "tags": sorted(tags),
                "score": row["loopability"] * len(tags) / len(vocab),
                "required_tags": sorted(tags & TIMBRES),
                "listening": "unreviewed",
            }
        )
    candidates.sort(key=lambda r: (-r["score"], r["id"]))
    reserved = [r for r in candidates if r["required_tags"]][: min(30, limit)]
    chosen = {r["id"] for r in reserved}
    selected = reserved + [r for r in candidates if r["id"] not in chosen][: limit - len(reserved)]
    return selected, {
        "pool": len(candidates),
        "tag_qualifying": sum(bool(r["required_tags"]) for r in candidates),
        "reserved": len(reserved),
        "required_track_target": 30,
        "audibly_verified": 0,
        "tag_shortfall": max(0, 30 - len(reserved)),
        "ranking": candidates,
    }


def audit(root: Path, limit: int) -> list[dict]:
    with db.connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute(
            """SELECT t.id,t.duration_s,max(w.loopability),array_agg(DISTINCT tag)
               FROM tracks t JOIN windows w ON w.track_id=t.id AND w.stem='mix'
               LEFT JOIN LATERAL unnest(w.tags) tag ON true
               WHERE t.source <> 'import' GROUP BY t.id,t.duration_s"""
        ).fetchall()
    selected, report = ranked(
        [{"id": r[0], "duration_s": r[1], "loopability": r[2], "tags": [t for t in r[3] if t]} for r in rows], limit
    )
    write_json(root / "audit.json", {"time": time.time(), **report, "selected": selected})
    emit(root, "audit", **{k: v for k, v in report.items() if k != "ranking"})
    return selected


def status(root: Path) -> dict:
    """Read-only counts, deliberately not a replacement for the later quality reporter."""
    with db.connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        report = {
            "time": time.time(),
            "counts": dict(
                conn.execute(
                    "SELECT 'tracks',count(*) FROM tracks UNION ALL SELECT 'windows',count(*) FROM windows "
                    "UNION ALL SELECT 'stems',count(*) FROM stems "
                    "UNION ALL SELECT 'heroes',count(*) FROM tracks WHERE is_hero"
                ).fetchall()
            ),
            "source_license": conn.execute(
                "SELECT source,license,count(*) FROM tracks GROUP BY source,license ORDER BY source,license"
            ).fetchall(),
            "stem_windows": conn.execute("SELECT stem,count(*) FROM windows GROUP BY stem ORDER BY stem").fetchall(),
            "jobs": conn.execute("SELECT status,count(*) FROM jobs GROUP BY status").fetchall(),
            "tag_qualifying_heroes": conn.execute(
                "SELECT count(DISTINCT t.id) FROM tracks t JOIN windows w ON w.track_id=t.id "
                "WHERE t.is_hero AND w.stem='mix' AND w.tags && %s",
                (sorted(TIMBRES),),
            ).fetchone()[0],
        }
    write_json(root / "status.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return report


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mix(data: Path, track_id: str) -> tuple[dict, Path]:
    directory = data / "tracks" / track_id
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["fingerprint"] != fingerprint():
        raise ValueError("Mix fingerprint differs; coordinate CLAP model/revision")
    validate(manifest, directory)
    return manifest, directory / "mix.mp3"


def activity_density(y: np.ndarray, stems: dict[str, np.ndarray], start: int, end: int) -> float:
    import librosa

    spectral = float(librosa.feature.spectral_flatness(y=y[start:end].mean(axis=1))[0].mean())
    active = sum(
        float(np.sqrt(np.mean(s[start:end].astype(np.float64) ** 2))) > 10 ** (-30 / 20) for s in stems.values()
    ) / len(STEMS)
    return float(np.clip((spectral + active) / 2, 0, 1))


def features(mix: dict, arrays: dict[str, np.ndarray]) -> tuple[list[dict], np.ndarray]:
    windows, chunks = [], []
    for stem in STEMS:
        y = arrays[stem].mean(axis=1)
        for piece in mix["offsets"]:
            start, end = round(piece["processed_start_s"] * SR), round(piece["processed_end_s"] * SR)
            feats = analysis.analyze_track(y[start:end], SR)
            for w in analysis.make_windows(y[start:end], SR, feats):
                w.start_s += start / SR
                w.end_s += start / SR
                a, b = round(w.start_s * SR), round(w.end_s * SR)
                w.density = activity_density(arrays[stem], arrays, a, b)
                windows.append({**asdict(w), "id": window_id(mix["id"], stem, w.start_s), "stem": stem})
                chunks.append(y[a:b])
    # Silence is dropped, never pad quiet stems into fictional searchable windows.
    if any(not any(w["stem"] == stem for w in windows) for stem in STEMS):
        raise ValueError("At least one stem has no audible searchable windows; hero gate unmet")
    vectors = clap.embed_audio(chunks, SR)
    for w, (tags, scores) in zip(windows, analysis.zero_shot_tags(vectors), strict=True):
        w.update(tags=tags, tag_scores=scores)
    return windows, vectors


def cached(directory: Path, identity: dict, mix: dict) -> tuple[dict, np.ndarray]:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["identity"] != identity:
        raise ValueError("Hero cache fingerprint differs; explicit migration required")
    with np.load(directory / "features.npz", allow_pickle=False) as archive:
        vectors = archive["embeddings"]
    windows = manifest["windows"]
    if (
        vectors.shape != (len(windows), 512)
        or not np.isfinite(vectors).all()
        or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4)
    ):
        raise ValueError("Invalid hero vectors")
    if set(manifest["hashes"]) != set(STEMS):
        raise ValueError("Missing cached stems")
    for stem in STEMS:
        path = directory / f"{stem}.mp3"
        if digest(path) != manifest["hashes"][stem]:
            raise ValueError("Hero audio hash mismatch")
        info = sf.info(path)
        if info.samplerate != SR or info.channels != 2 or abs(info.duration - mix["duration_s"]) > 0.01:
            raise ValueError("Hero audio format/coverage mismatch")
        if not any(w["stem"] == stem for w in windows):
            raise ValueError("Missing audible stem windows")
    ids = set()
    for w in windows:
        if (
            w["stem"] not in STEMS
            or not 0 <= w["start_s"] < w["end_s"] <= mix["duration_s"]
            or not np.isfinite([w["start_s"], w["end_s"], w["rms"], w["loopability"], w["density"]]).all()
            or not 0 <= w["density"] <= 1
            or not 0 <= w["loopability"] <= 1
            or w["rms"] < 10 ** (-45 / 20)
            or not w["tag_scores"]
            or not np.isfinite(list(w["tag_scores"].values())).all()
            or w["id"] != window_id(mix["id"], w["stem"], w["start_s"])
            or w["id"] in ids
            or any(w["start_s"] < p["processed_end_s"] < w["end_s"] for p in mix["offsets"])
        ):
            raise ValueError("Invalid hero window")
        ids.add(w["id"])
    return manifest, vectors


def prepare(data: Path, root: Path, track_id: str, engine: Engine) -> tuple[dict, dict, np.ndarray]:
    mix, path = load_mix(data, track_id)
    directory = root / track_id
    directory.mkdir(exist_ok=True)
    identity = {
        "mix_sha256": mix["audio_sha256"],
        "pipeline": fingerprint(),
        "separation": engine.identity,
        "hero_pipeline": "1",
    }
    if (directory / "manifest.json").exists():
        previous = json.loads((directory / "manifest.json").read_text())
        if previous["identity"] != identity:
            raise ValueError("Hero cache fingerprint differs; explicit migration required")
        try:
            manifest, vectors = cached(directory, identity, mix)
            return mix, manifest, vectors
        except (ValueError, OSError, EOFError, KeyError):
            emit(root, "cache_repair", id=track_id)
    # Raw stems are checkpointed independently of features/publication for resumable long inference.
    raw_manifest = directory / "separated.json"
    if raw_manifest.exists() and json.loads(raw_manifest.read_text())["identity"] != identity:
        raise ValueError("Separation fingerprint differs")
    resumed = False
    if raw_manifest.exists():
        previous = json.loads(raw_manifest.read_text())
        resumed = all(
            (directory / f"{s}.mp3").exists() and digest(directory / f"{s}.mp3") == h
            for s, h in previous["hashes"].items()
        ) and set(previous["hashes"]) == set(STEMS)
    if not resumed:
        emit(root, "separation_start", id=track_id, duration_s=mix["duration_s"])
        arrays, timing = engine.separate(stereo(path))
        for stem in STEMS:
            encode(arrays[stem], directory / f"{stem}.mp3")
        write_json(
            raw_manifest,
            {"identity": identity, "timing": timing, "hashes": {s: digest(directory / f"{s}.mp3") for s in STEMS}},
        )
        emit(root, "separation_done", id=track_id, **timing)
    previous = json.loads(raw_manifest.read_text())
    arrays = {s: stereo(directory / f"{s}.mp3") for s in STEMS}
    windows, vectors = features(mix, arrays)
    manifest = {"identity": identity, "hashes": previous["hashes"], "windows": windows, "timing": previous["timing"]}
    np.savez_compressed(directory / "features.npz", embeddings=vectors)
    write_json(directory / "manifest.json", manifest)
    cached(directory, identity, mix)
    return mix, manifest, vectors


def verify(mix: dict, manifest: dict, vectors: np.ndarray, client: httpx.Client) -> bool:
    tid = mix["id"]
    with db.connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        hero = conn.execute("SELECT is_hero FROM tracks WHERE id=%s", (tid,)).fetchone()
        stems = conn.execute(
            "SELECT stem,range_start_s,range_end_s,path,model FROM stems WHERE track_id=%s", (tid,)
        ).fetchall()
        rows = conn.execute(
            """SELECT id,stem,start_s,end_s,tags,tag_scores,loopability,rms,density,embedding
               FROM windows WHERE track_id=%s AND stem=ANY(%s)""",
            (tid, list(STEMS)),
        ).fetchall()
    if not hero or not hero[0] or {r[0] for r in rows} != {w["id"] for w in manifest["windows"]}:
        return False
    expected = {w["id"]: (w, v) for w, v in zip(manifest["windows"], vectors, strict=True)}
    for row in rows:
        w, vector = expected[row[0]]
        if (
            row[1] != w["stem"]
            or row[4] != w["tags"]
            or row[5] != w["tag_scores"]
            or not np.allclose(
                [row[2], row[3], *row[6:9]],
                [w["start_s"], w["end_s"], w["loopability"], w["rms"], w["density"]],
                atol=1e-5,
            )
            or not np.allclose(row[9].to_numpy(), vector, atol=1e-6)
        ):
            return False
    for stem in STEMS:
        path = f"tracks/{tid}/stems/{stem}.mp3"
        if not any(
            r[0] == stem and r[1] == 0 and abs(r[2] - mix["duration_s"]) < 0.01 and r[3] == path and r[4] == "htdemucs"
            for r in stems
        ):
            return False
        response = client.get(storage.public_url(path))
        if not response.is_success or hashlib.sha256(response.content).hexdigest() != manifest["hashes"][stem]:
            return False
    return True


def publish(root: Path, mix: dict, manifest: dict, vectors: np.ndarray, client: httpx.Client) -> str:
    if verify(mix, manifest, vectors, client):
        return "verified_existing"
    tid = mix["id"]
    for stem in STEMS:
        path = f"tracks/{tid}/stems/{stem}.mp3"
        storage.upload(str(root / tid / f"{stem}.mp3"), path, "audio/mpeg")
        response = client.get(storage.public_url(path))
        if not response.is_success or hashlib.sha256(response.content).hexdigest() != manifest["hashes"][stem]:
            raise ValueError("Public stem verification failed")
    with db.connect() as conn:
        for stem in STEMS:
            conn.execute(
                """INSERT INTO stems(track_id,stem,range_start_s,range_end_s,path,model)
                   VALUES(%s,%s,0,%s,%s,'htdemucs') ON CONFLICT(track_id,stem,range_start_s,range_end_s)
                   DO UPDATE SET path=excluded.path,model=excluded.model""",
                (tid, stem, mix["duration_s"], f"tracks/{tid}/stems/{stem}.mp3"),
            )
        for w, vector in zip(manifest["windows"], vectors, strict=True):
            conn.execute(
                """INSERT INTO windows(id,track_id,stem,start_s,end_s,embedding,tags,tag_scores,loopability,rms,density)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET
                   start_s=excluded.start_s,end_s=excluded.end_s,embedding=excluded.embedding,tags=excluded.tags,
                   tag_scores=excluded.tag_scores,loopability=excluded.loopability,rms=excluded.rms,density=excluded.density""",
                (
                    w["id"],
                    tid,
                    w["stem"],
                    w["start_s"],
                    w["end_s"],
                    vector,
                    w["tags"],
                    Jsonb(w["tag_scores"]),
                    w["loopability"],
                    w["rms"],
                    w["density"],
                ),
            )
        conn.execute(
            "DELETE FROM windows WHERE track_id=%s AND stem=ANY(%s) AND NOT(id=ANY(%s))",
            (tid, list(STEMS), [w["id"] for w in manifest["windows"]]),
        )
        conn.execute("UPDATE tracks SET is_hero=true WHERE id=%s", (tid,))
    if not verify(mix, manifest, vectors, client):
        raise ValueError("Post-publication hero verification failed")
    return "published"


def benchmark(data: Path, root: Path, tid: str, engine: Engine) -> None:
    mix, path = load_mix(data, tid)
    y = stereo(path)
    if len(y) < 180 * SR:
        raise ValueError("Benchmark requires a real 180-second processed mix")
    results = []
    for seconds in (30, 180):
        start = time.perf_counter()
        _, timing = engine.separate(y[: seconds * SR])
        result = {
            "track_id": tid,
            "duration_s": seconds,
            **timing,
            "wall_s": time.perf_counter() - start,
            "model_load_s": engine.load_s,
            "identity": engine.identity,
            "scope": "local decoded stereo inference; excludes download/encode/embedding/upload/DB",
        }
        results.append(result)
        write_json(root / "benchmarks.json", results)
        emit(root, "benchmark", **result)


def run(data: Path, root: Path, limit: int, mode: str, tid: str | None) -> None:
    if mode == "status":
        status(root)
        return
    if mode == "audit":
        audit(root, limit)
        return
    engine = Engine()
    emit(root, "engine", pid=os.getpid(), device=engine.device, load_s=engine.load_s, identity=engine.identity)
    if mode == "benchmark":
        if tid is None:
            raise ValueError("--track is required for benchmark")
        benchmark(data, root, tid, engine)
        return
    if mode == "verify":
        ids = [tid] if tid else [p.parent.name for p in root.glob("*/manifest.json")]
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            for track_id in ids:
                mix, _ = load_mix(data, track_id)
                directory = root / track_id
                identity = {
                    "mix_sha256": mix["audio_sha256"],
                    "pipeline": fingerprint(),
                    "separation": engine.identity,
                    "hero_pipeline": "1",
                }
                manifest, vectors = cached(directory, identity, mix)
                if not verify(mix, manifest, vectors, client):
                    raise ValueError(f"Hero verification failed: {track_id}")
                emit(root, "verified", id=track_id, windows=len(manifest["windows"]))
        return
    queue_path = root / "queue.json"
    if tid is not None:
        queue = [tid]
    elif queue_path.exists():
        queue = json.loads(queue_path.read_text())
    else:
        queue = [r["id"] for r in audit(root, limit)]
        # Keep ranked spares so a silent stem or a failed candidate cannot silently lower the target.
        report = json.loads((root / "audit.json").read_text())
        queue += [r["id"] for r in report["ranking"] if r["id"] not in queue][:20]
        write_json(queue_path, queue)
    if len(queue) < limit and tid is None:
        raise ValueError("Candidate pool below target; rerun audit after more mix ingest")
    start = time.perf_counter()
    completed, failed = 0, 0
    measured = []
    if (root / "heroes.log").exists():
        for line in (root / "heroes.log").read_text().splitlines():
            event = json.loads(line)
            if event["event"] == "hero" and event["outcome"] == "published":
                measured.append(event["seconds"])
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for track_id in queue:
            if completed >= limit:
                break
            began = time.perf_counter()
            try:
                mix, manifest, vectors = prepare(data, root, track_id, engine)
                outcome = publish(root, mix, manifest, vectors, client)
                completed += 1
                if outcome == "published":
                    measured.append(time.perf_counter() - began)
                emit(
                    root,
                    "hero",
                    id=track_id,
                    outcome=outcome,
                    windows=len(manifest["windows"]),
                    seconds=time.perf_counter() - began,
                    inference=manifest["timing"],
                )
            except Exception as error:
                failed += 1
                emit(root, "failure", id=track_id, **failure_details(error), message=str(error)[:200])
            elapsed = time.perf_counter() - start
            emit(
                root,
                "progress",
                target=limit,
                completed=completed,
                failed=failed,
                elapsed_s=elapsed,
                eta_s=float(np.mean(measured[-10:])) * (limit - completed) if measured else None,
                eta_basis="last ten newly published heroes; source-duration mix may change",
            )
    emit(root, "finished", completed=completed, failed=failed, target=limit)
    if failed or completed < limit:
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["audit", "status", "benchmark", "batch", "verify"], default="batch")
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--track")
    parser.add_argument("--data-dir", type=Path, default=Path("ingest/data"))
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 80:
        parser.error("--limit must be 1..80")
    if clap.CLAP_MODEL == "laion/larger_clap_music" or clap.CLAP_REVISION == "main":
        parser.error("Coordinate the approved immutable CLAP model/revision first")
    root = args.data_dir / "heroes"
    root.mkdir(parents=True, exist_ok=True)
    if args.mode in {"status", "verify"}:
        run(args.data_dir, root, args.limit, args.mode, args.track)
        return
    with (root / "heroes.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.data_dir, root, args.limit, args.mode, args.track)


if __name__ == "__main__":
    main()
