"""Recoverable per-track publication: upload before one DB transaction."""

import hashlib
import json
import time
import zipfile
from dataclasses import asdict
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf
from psycopg.types.json import Jsonb

from common import analysis, audio, clap, db, storage
from common.ids import window_id
from ingest.sources import Candidate, write_json

SR = 44100


def fingerprint() -> dict[str, str]:
    return {
        "pipeline": "1",
        "model": clap.CLAP_MODEL,
        "revision": clap.CLAP_REVISION,
        "vocab": hashlib.sha256((Path(__file__).parent / "vocab.txt").read_bytes()).hexdigest(),
    }


def excerpt_ranges(duration: float) -> list[tuple[float, float]]:
    if duration <= 180:
        return [(0, duration)]
    middle = min(duration - 60, max(120, duration / 2 - 30))
    return [(0, 120), (middle, middle + 60)]


def download(client: httpx.Client, url: str, path: Path) -> None:
    temporary = path.with_suffix(".part")
    for attempt in range(3):
        try:
            with client.stream("GET", url) as response, temporary.open("wb") as output:
                response.raise_for_status()
                size = 0
                for block in response.iter_bytes(65536):
                    size += len(block)
                    if size > 100 * 1024 * 1024:
                        raise ValueError("Download exceeds 100 MiB limit")
                    output.write(block)
            audio.load_mono(str(temporary))
            temporary.replace(path)
            return
        except (httpx.HTTPError, ValueError):
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def prepare(item: Candidate, directory: Path, client: httpx.Client) -> dict:
    manifest_path = directory / "manifest.json"
    identity = {"fingerprint": fingerprint(), "source": item.metadata()}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(manifest[key] != identity[key] for key in identity):
            raise ValueError("Cached track fingerprint/source differs; explicit migration required")
        if all((directory / name).exists() for name in ("mix.mp3", "features.npz")):
            try:
                validate(manifest, directory)
                return manifest
            except (ValueError, OSError, EOFError, zipfile.BadZipFile, KeyError):
                pass
    original = directory / "original.audio"
    if original.exists():
        try:
            audio.load_mono(str(original))
        except ValueError:
            original.unlink()
    if not original.exists():
        download(client, item.download_url, original)
    y, sr = audio.load_mono(str(original))
    ranges = excerpt_ranges(len(y) / sr)
    stereo_path = directory / "decoded.wav"
    audio._ffmpeg(
        [
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(original.resolve()),
            "-vn",
            "-ar",
            str(SR),
            "-ac",
            "2",
            "-c:a",
            "pcm_f32le",
            "-y",
            str(stereo_path.resolve()),
        ]
    )
    channels, _ = sf.read(stereo_path, dtype="float32", always_2d=True)
    pieces = [channels[round(start * sr) : round(end * sr)] for start, end in ranges]
    wav = directory / "processed.wav"
    sf.write(wav, np.concatenate(pieces), sr, subtype="FLOAT")
    audio.to_mp3(str(wav), str(directory / "mix.mp3"))
    playable, _ = audio.load_mono(str(directory / "mix.mp3"))
    windows, beats, features, offsets = [], [], [], []
    offset = 0
    for (source_start, source_end), piece in zip(ranges, pieces, strict=True):
        end = min(offset + len(piece), len(playable))
        segment = playable[offset:end]
        feats = analysis.analyze_track(segment, sr)
        features.append(feats)
        for window in analysis.make_windows(segment, sr, feats):
            window.start_s += offset / sr
            window.end_s += offset / sr
            windows.append(window)
        beats.extend(beat + offset / sr for beat in feats.beat_times)
        offsets.append(
            {
                "source_start_s": source_start,
                "source_end_s": source_end,
                "processed_start_s": offset / sr,
                "processed_end_s": end / sr,
            }
        )
        offset = end
    if not windows:
        raise ValueError("No audible searchable windows")
    embeddings = clap.embed_audio([playable[round(w.start_s * sr) : round(w.end_s * sr)] for w in windows], sr)
    tags = analysis.zero_shot_tags(embeddings)
    tempos = [f.bpm for f in features if f.bpm is not None]
    bpm = float(np.median(tempos)) if tempos and max(tempos) / min(tempos) < 1.2 else None
    manifest = {
        **identity,
        "id": item.id,
        "duration_s": len(playable) / sr,
        "bpm": bpm,
        "key": features[0].key,
        "beat_times": beats,
        "offsets": offsets,
        "windows": [
            {**asdict(w), "id": window_id(item.id, "mix", w.start_s), "tags": t[0], "tag_scores": t[1]}
            for w, t in zip(windows, tags, strict=True)
        ],
        "audio_sha256": hashlib.sha256((directory / "mix.mp3").read_bytes()).hexdigest(),
        "attribution": f"{item.title} by {item.artist}; {item.source_url}; {item.license} "
        f"({item.license_url}); excerpted/transcoded by Beatopia.",
    }
    np.savez_compressed(directory / "features.npz", embeddings=embeddings)
    validate(manifest, directory)
    write_json(manifest_path, manifest)
    wav.unlink(missing_ok=True)
    stereo_path.unlink(missing_ok=True)
    return manifest


def validate(manifest: dict, directory: Path) -> np.ndarray:
    with np.load(directory / "features.npz", allow_pickle=False) as archive:
        vectors = archive["embeddings"]
    windows = manifest["windows"]
    if (
        not windows
        or vectors.shape != (len(windows), 512)
        or not np.isfinite(vectors).all()
        or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4)
    ):
        raise ValueError("Invalid cached vectors")
    if hashlib.sha256((directory / "mix.mp3").read_bytes()).hexdigest() != manifest["audio_sha256"]:
        raise ValueError("Cached audio hash mismatch")
    if not manifest["attribution"].strip():
        raise ValueError("Missing attribution")
    ids = set()
    for w in windows:
        if (
            not np.isfinite([w["start_s"], w["end_s"], w["rms"], w["loopability"], w["density"]]).all()
            or not 0 <= w["start_s"] < w["end_s"] <= manifest["duration_s"]
            or not 0 <= w["loopability"] <= 1
            or not 0 <= w["density"] <= 1
            or any(w["start_s"] < p["processed_end_s"] < w["end_s"] for p in manifest["offsets"])
            or w["id"] != window_id(manifest["id"], "mix", w["start_s"])
            or w["id"] in ids
            or not w["tag_scores"]
            or not np.isfinite(list(w["tag_scores"].values())).all()
        ):
            raise ValueError("Invalid cached window")
        ids.add(w["id"])
    return vectors


def published(manifest: dict, client: httpx.Client, vectors: np.ndarray) -> bool:
    with db.connect() as conn:
        track = conn.execute(
            "SELECT duration_s,attribution,audio_path FROM tracks WHERE id=%s", (manifest["id"],)
        ).fetchone()
        rows = conn.execute(
            """SELECT id,embedding,start_s,end_s,tags,tag_scores,loopability,rms,density
               FROM windows WHERE track_id=%s AND stem='mix' ORDER BY id""",
            (manifest["id"],),
        ).fetchall()
    if (
        not track
        or abs(track[0] - manifest["duration_s"]) > 0.01
        or track[1] != manifest["attribution"]
        or track[2] != f"tracks/{manifest['id']}/mix.mp3"
        or {r[0] for r in rows} != {w["id"] for w in manifest["windows"]}
    ):
        return False
    expected = {w["id"]: (w, vector) for w, vector in zip(manifest["windows"], vectors, strict=True)}
    for row in rows:
        w, vector = expected[row[0]]
        if (
            not np.allclose(row[1].to_numpy(), vector, atol=1e-6)
            or not np.allclose(
                [row[2], row[3], *row[6:]],
                [w["start_s"], w["end_s"], w["loopability"], w["rms"], w["density"]],
                atol=1e-5,
            )
            or row[4] != w["tags"]
            or row[5] != w["tag_scores"]
        ):
            return False
    try:
        response = client.get(storage.public_url(track[2]))
        return response.is_success and hashlib.sha256(response.content).hexdigest() == manifest["audio_sha256"]
    except httpx.TransportError:
        return False


def publish(item: Candidate, manifest: dict, directory: Path, client: httpx.Client) -> str:
    vectors = validate(manifest, directory)
    if published(manifest, client, vectors):
        return "verified_existing"
    path = f"tracks/{item.id}/mix.mp3"
    storage.upload(str(directory / "mix.mp3"), path, "audio/mpeg")
    response = client.get(storage.public_url(path))
    if not response.is_success or hashlib.sha256(response.content).hexdigest() != manifest["audio_sha256"]:
        raise ValueError("Public uploaded audio verification failed")
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO tracks(id,source,source_id,source_url,title,artist,license,attribution,
               duration_s,bpm,key,beat_times,audio_path) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(id) DO UPDATE SET source_url=excluded.source_url,title=excluded.title,
               artist=excluded.artist,license=excluded.license,attribution=excluded.attribution,
               duration_s=excluded.duration_s,bpm=excluded.bpm,key=excluded.key,
               beat_times=excluded.beat_times,audio_path=excluded.audio_path""",
            (
                item.id,
                item.source,
                item.source_id,
                item.source_url,
                item.title,
                item.artist,
                item.license,
                manifest["attribution"],
                manifest["duration_s"],
                manifest["bpm"],
                manifest["key"],
                manifest["beat_times"],
                path,
            ),
        )
        for w, vector in zip(manifest["windows"], vectors, strict=True):
            conn.execute(
                """INSERT INTO windows(id,track_id,stem,start_s,end_s,embedding,tags,tag_scores,loopability,rms,density)
                   VALUES(%s,%s,'mix',%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET
                   start_s=excluded.start_s,end_s=excluded.end_s,embedding=excluded.embedding,tags=excluded.tags,
                   tag_scores=excluded.tag_scores,loopability=excluded.loopability,rms=excluded.rms,
                   density=excluded.density""",
                (
                    w["id"],
                    item.id,
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
            "DELETE FROM windows WHERE track_id=%s AND stem='mix' AND NOT(id=ANY(%s))",
            (item.id, [w["id"] for w in manifest["windows"]]),
        )
    return "published"


def process(item: Candidate, root: Path, client: httpx.Client) -> str:
    directory = root / "tracks" / item.id
    directory.mkdir(parents=True, exist_ok=True)
    manifest = prepare(item, directory, client)
    return publish(item, manifest, directory, client)
