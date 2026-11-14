"""Full-timeline import normalization and indexed mix windows; imports stay private."""

import json
import re
import time
import zipfile
from dataclasses import asdict
from pathlib import Path

import httpx
import numpy as np
from psycopg.types.json import Jsonb

from common import analysis, audio, clap, db, storage
from common.ids import window_id
from worker.handlers import (
    SR,
    TRACK_KEYS,
    Progress,
    digest,
    download,
    identifier,
    playable,
    read_track,
    stem_output,
    write_json,
)
from worker.jobs import track_lock


def track_detail(tid: str) -> dict:
    track = read_track(tid)
    with db.connect() as conn:
        windows = conn.execute(
            """SELECT id,track_id,stem,start_s,end_s,tags,loopability,rms,density
               FROM windows WHERE track_id=%s ORDER BY start_s,stem,id""",
            (tid,),
        ).fetchall()
        stems = conn.execute(
            "SELECT stem,range_start_s,range_end_s,path,model FROM stems WHERE track_id=%s ORDER BY stem,range_start_s",
            (tid,),
        ).fetchall()
    keys = "id,track_id,stem,start_s,end_s,tags,loopability,rms,density".split(",")
    return {
        "track": {key: track[key] for key in TRACK_KEYS},
        "audio_url": storage.public_url(track["audio_path"]),
        "beat_times": track["beat_times"],
        "windows": [dict(zip(keys, row, strict=True)) for row in windows],
        "stems": [stem_output(tid, *row) for row in stems],
    }


def validate(manifest: dict, directory: Path) -> np.ndarray:
    with np.load(directory / "features.npz", allow_pickle=False) as data:
        vectors = data["embeddings"]
    windows = manifest["windows"]
    if (
        not windows
        or vectors.shape != (len(windows), 512)
        or not np.isfinite(vectors).all()
        or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4)
    ):
        raise ValueError("Invalid import window embeddings")
    if digest(directory / "mix.mp3") != manifest["audio_sha256"]:
        raise ValueError("Import mix cache hash mismatch")
    duration = manifest["duration_s"]
    playable(directory / "mix.mp3", duration)
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid import duration")
    if any(not np.isfinite(t) or not 0 <= t < duration for t in manifest["beat_times"]):
        raise ValueError("Invalid import beats")
    seen = set()
    for w in windows:
        if (
            not np.isfinite([w["start_s"], w["end_s"], w["rms"], w["loopability"], w["density"]]).all()
            or not 0 <= w["start_s"] < w["end_s"] <= duration
            or w["rms"] < 10 ** (-45 / 20)
            or not 0 <= w["loopability"] <= 1
            or not 0 <= w["density"] <= 1
            or w["id"] != window_id(manifest["id"], "mix", w["start_s"])
            or w["id"] in seen
            or not w["tag_scores"]
            or not np.isfinite(list(w["tag_scores"].values())).all()
        ):
            raise ValueError("Invalid imported window")
        seen.add(w["id"])
    return vectors


def prepare(tid: str, original: Path, directory: Path, timings: dict) -> tuple[dict, np.ndarray]:
    identity = {
        "pipeline": "worker-import-1",
        "source_sha256": digest(original),
        "clap": clap.CLAP_MODEL,
        "revision": clap.CLAP_REVISION,
        "vocab": analysis._vocab(),
    }
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        if saved["identity"] != identity:
            raise ValueError("Import checkpoint identity changed; explicit migration required")
        try:
            vectors = validate(saved, directory)
            timings["analysis_reused"] = True
            return saved, vectors
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
            pass
    started = time.perf_counter()
    audio.to_mp3(str(original), str(directory / "mix.mp3"))
    y, sr = audio.load_mono(str(directory / "mix.mp3"), SR)
    feats = analysis.analyze_track(y, sr)
    windows = analysis.make_windows(y, sr, feats)
    if not windows:
        raise ValueError("Import contains no audible searchable windows")
    vectors = clap.embed_audio([y[round(w.start_s * sr) : round(w.end_s * sr)] for w in windows], sr)
    tags = analysis.zero_shot_tags(vectors)
    manifest = {
        "identity": identity,
        "id": tid,
        **asdict(feats),
        "audio_sha256": digest(directory / "mix.mp3"),
        "windows": [
            {**asdict(w), "id": window_id(tid, "mix", w.start_s), "tags": tag, "tag_scores": scores}
            for w, (tag, scores) in zip(windows, tags, strict=True)
        ],
    }
    temporary = directory / "features.tmp.npz"
    np.savez_compressed(temporary, embeddings=vectors)
    temporary.replace(directory / "features.npz")
    validate(manifest, directory)
    write_json(manifest_path, manifest)
    timings["normalize_analyze_embed_s"] = time.perf_counter() - started
    return manifest, vectors


def analyze(data: dict, root: Path, update: Progress, timings: dict) -> dict:
    if not isinstance(data, dict) or set(data) != {"track_id", "path"}:
        raise ValueError("Invalid analyze job input")
    tid = identifier(data["track_id"])
    if (
        not tid.startswith("imp_")
        or not isinstance(data["path"], str)
        or not re.fullmatch(
            rf"imports/{re.escape(tid)}/original\.(wav|mp3|flac|m4a|ogg)",
            data["path"],
        )
    ):
        raise ValueError("Analyze path must be this import's original audio")
    with track_lock(tid), httpx.Client(timeout=60, follow_redirects=True) as client:
        track = read_track(tid)
        if track["source"] != "import" or not track["license"].strip() or not track["attribution"].strip():
            raise ValueError("Analyze requires an import placeholder with license and attribution")
        directory = root / "imports" / tid
        directory.mkdir(parents=True, exist_ok=True)
        original = directory / "original.audio"
        update(0.05)
        download(client, data["path"], original, 25 * 1024 * 1024)
        update(0.15)
        manifest, vectors = prepare(tid, original, directory, timings)
        update(0.75)
        path = f"imports/{tid}/mix.mp3"
        storage.upload(str(directory / "mix.mp3"), path, "audio/mpeg")
        public = directory / "public.mp3"
        download(client, path, public)
        if digest(public) != manifest["audio_sha256"]:
            raise ValueError("Public import mix hash mismatch")
        update(0.9)
        with db.connect() as conn:
            # Never replace WS2's title/artist/source/license/attribution with invented metadata.
            conn.execute(
                """UPDATE tracks SET duration_s=%s,bpm=%s,key=%s,beat_times=%s,audio_path=%s
                   WHERE id=%s AND source='import'""",
                (manifest["duration_s"], manifest["bpm"], manifest["key"], manifest["beat_times"], path, tid),
            )
            conn.execute(
                "DELETE FROM windows WHERE track_id=%s AND stem='mix' AND NOT(id=ANY(%s))",
                (tid, [w["id"] for w in manifest["windows"]]),
            )
            for w, vector in zip(manifest["windows"], vectors, strict=True):
                conn.execute(
                    """INSERT INTO windows(id,track_id,stem,start_s,end_s,embedding,tags,tag_scores,
                       loopability,rms,density)
                       VALUES(%s,%s,'mix',%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET
                       start_s=excluded.start_s,end_s=excluded.end_s,embedding=excluded.embedding,tags=excluded.tags,
                       tag_scores=excluded.tag_scores,loopability=excluded.loopability,rms=excluded.rms,density=excluded.density""",
                    (
                        w["id"],
                        tid,
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
        update(0.95)
        return {"track": track_detail(tid)}
