"""Storage-backed stem jobs. Publication follows successful uploads and verification."""

import hashlib
import json
import math
import re
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

from common import audio, db, storage
from worker.engine import MODELS, SR, Engine, engine
from worker.jobs import track_lock

Progress = Callable[[float], None]
TRACK_COLUMNS = "id,title,artist,source,source_url,license,attribution,duration_s,bpm,key,is_hero"
TRACK_KEYS = TRACK_COLUMNS.split(",")


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z]+_[A-Za-z0-9-]+", value):
        raise ValueError("Invalid track ID")
    return value


def read_track(track_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            f"SELECT {TRACK_COLUMNS},audio_path,beat_times FROM tracks WHERE id=%s", (track_id,)
        ).fetchone()
    if row is None:
        raise ValueError("Track does not exist")
    return {**dict(zip(TRACK_KEYS, row[:11], strict=True)), "audio_path": row[11], "beat_times": row[12]}


def bounds(data: dict, duration: float) -> tuple[float, float, str]:
    if set(data) != {"track_id", "start_s", "end_s", "model"} or data["model"] not in MODELS:
        raise ValueError("Invalid stems job input/model")
    start, end = data["start_s"], data["end_s"]
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in (start, end)):
        raise ValueError("Range must contain finite numbers")
    if not math.isfinite(duration) or not 0 <= start < end <= duration or end - start > 60:
        raise ValueError("Range must be inside the track and at most 60 seconds")
    return float(start), float(end), data["model"]


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(client: httpx.Client, path: str, local: Path, limit: int = 100 * 1024 * 1024) -> None:
    temporary = local.with_suffix(".part")
    try:
        with client.stream("GET", storage.public_url(path)) as response, temporary.open("wb") as out:
            response.raise_for_status()
            size = 0
            for block in response.iter_bytes(65536):
                size += len(block)
                if size > limit:
                    raise ValueError("Audio exceeds download size limit")
                out.write(block)
        temporary.replace(local)
    finally:
        temporary.unlink(missing_ok=True)


def playable(path: Path, duration: float) -> None:
    info = sf.info(path)
    if info.samplerate != SR or info.channels != 2 or abs(info.duration - duration) > 0.025:
        raise ValueError("Playable audio format/duration differs from coverage")
    # Decode too: container metadata alone does not establish playable finite audio.
    y, _ = audio.load_mono(str(path))
    if abs(len(y) / SR - duration) > 0.025:
        raise ValueError("Decoded duration differs from coverage")


def stem_output(track_id: str, stem: str, start: float, end: float, path: str, model: str) -> dict:
    return {
        "track_id": track_id,
        "stem": stem,
        "range_start_s": start,
        "range_end_s": end,
        "url": storage.public_url(path),
        "model": model,
    }


def covering(
    client: httpx.Client, directory: Path, tid: str, start: float, end: float, model: str
) -> list[dict] | None:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT stem,range_start_s,range_end_s,path FROM stems
               WHERE track_id=%s AND model=%s AND range_start_s<=%s::real AND range_end_s>=%s::real
               ORDER BY range_end_s-range_start_s,range_start_s,stem""",
            (tid, model, start, end),
        ).fetchall()
    groups: dict[tuple[float, float], dict] = {}
    for stem, first, last, path in rows:
        groups.setdefault((first, last), {})[stem] = path
    for (first, last), paths in groups.items():
        if set(paths) != set(MODELS[model]):
            continue
        try:
            for stem, path in paths.items():
                local = directory / f"verify-{stem}.mp3"
                download(client, path, local)
                playable(local, last - first)
        except (httpx.HTTPError, ValueError, OSError, RuntimeError):
            continue
        return [stem_output(tid, stem, first, last, paths[stem], model) for stem in MODELS[model]]
    return None


def raw_stems(
    directory: Path, identity: dict, y: np.ndarray, separator: Engine, timings: dict
) -> dict[str, np.ndarray]:
    manifest = directory / "separated.json"
    archive = directory / "separated.npz"
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        if saved["identity"] != identity:
            raise ValueError("Stem checkpoint identity changed; explicit migration required")
        try:
            if digest(archive) == saved["sha256"]:
                with np.load(archive, allow_pickle=False) as data:
                    result = {name: data[name] for name in data.files}
                if set(result) == set(MODELS[identity["engine"]["model"]]) and all(
                    value.shape == y.shape and np.isfinite(value).all() for value in result.values()
                ):
                    timings["separation_reused"] = True
                    return result
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
            pass
    result, measured = separator.separate(y)
    timings.update(measured)
    temporary = directory / "separated.tmp.npz"
    np.savez_compressed(temporary, **result)
    temporary.replace(archive)
    write_json(manifest, {"identity": identity, "sha256": digest(archive)})
    return result


def stems_job(data: dict, root: Path, update: Progress, timings: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Job input must be an object")
    tid = identifier(data.get("track_id"))
    with track_lock(tid), httpx.Client(timeout=60, follow_redirects=True) as client:
        track = read_track(tid)
        start, end, model = bounds(data, track["duration_s"])
        directory = root / "stems" / tid / hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        directory.mkdir(parents=True, exist_ok=True)
        update(0.05)
        found = covering(client, directory, tid, start, end, model)
        if found is not None:
            timings["covering_cache_reused"] = True
            update(0.95)
            return {"stems": found}
        started = time.perf_counter()
        mix = directory / "mix.mp3"
        download(client, track["audio_path"], mix)
        raw = audio._ffmpeg(
            [
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(mix.resolve()),
                "-ss",
                str(start),
                "-t",
                str(end - start),
                "-vn",
                "-ar",
                str(SR),
                "-ac",
                "2",
                "-f",
                "f32le",
                "pipe:1",
            ]
        )
        y = np.frombuffer(raw, dtype="<f4").reshape(-1, 2).copy()
        if abs(len(y) / SR - (end - start)) > 1 / SR or not np.isfinite(y).all():
            raise ValueError("Requested range exceeds decoded mix or contains invalid samples")
        timings["download_decode_s"] = time.perf_counter() - started
        update(0.15)
        separator = engine(model)
        timings["model_load_s"] = separator.load_s
        identity = {"engine": separator.identity, "audio_sha256": digest(mix), "start": start, "end": end}
        arrays = raw_stems(directory, identity, y, separator, timings)
        update(0.65)
        output, paths = [], []
        for index, stem in enumerate(MODELS[model]):
            local = directory / f"{stem}.mp3"
            wav = directory / f"{stem}.wav"
            sf.write(wav, arrays[stem], SR, subtype="FLOAT")
            audio.to_mp3(str(wav), str(local))
            playable(local, end - start)
            path = f"tracks/{tid}/stems/{stem}_{round(start * 1000)}_{round(end * 1000)}.mp3"
            # Contract filenames round to ms. Never overwrite a different sub-ms coverage.
            with db.connect() as conn:
                collision = conn.execute(
                    """SELECT 1 FROM stems WHERE path=%s AND
                       (range_start_s<>%s::real OR range_end_s<>%s::real OR model<>%s)""",
                    (path, start, end, model),
                ).fetchone()
            if collision:
                raise ValueError("Range storage path already represents different coverage/model")
            storage.upload(str(local), path, "audio/mpeg")
            public = directory / f"public-{stem}.mp3"
            download(client, path, public)
            if digest(public) != digest(local):
                raise ValueError("Public stem hash differs from uploaded audio")
            paths.append((tid, stem, start, end, path, model))
            output.append(stem_output(tid, stem, start, end, path, model))
            update(0.65 + 0.3 * (index + 1) / len(MODELS[model]))
        with db.connect() as conn:
            for values in paths:
                conn.execute(
                    """INSERT INTO stems(track_id,stem,range_start_s,range_end_s,path,model)
                       VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(track_id,stem,range_start_s,range_end_s)
                       DO UPDATE SET path=excluded.path,model=excluded.model""",
                    values,
                )
        return {"stems": output}


def analyze_job(data: dict, root: Path, update: Progress, timings: dict) -> dict:
    from worker.imports import analyze

    return analyze(data, root, update, timings)
