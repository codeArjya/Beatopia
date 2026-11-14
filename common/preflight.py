"""Runtime and optional live-service checks: python -m common.preflight [--live]."""

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import soundfile as sf
import torch
from supabase import create_client

from common.audio import load_mono, to_mp3
from common.db import connect
from common.storage import BUCKET, upload


def check_database() -> dict[str, object]:
    vector = np.zeros(512, dtype=np.float32)
    vector[0] = 1
    with connect() as connection:
        row = connection.execute("SELECT %s::vector", (vector,)).fetchone()
        if row is None or not np.array_equal(row[0].to_numpy(), vector):
            raise RuntimeError("pgvector roundtrip failed")
        counts = {}
        # Literal queries only; also verify that the bootstrap schema exists.
        for name, query in (
            ("tracks", "SELECT count(*) FROM tracks"),
            ("windows", "SELECT count(*) FROM windows"),
            ("stems", "SELECT count(*) FROM stems"),
        ):
            result = connection.execute(query).fetchone()
            counts[name] = result[0] if result else None
    return {"vector_roundtrip": True, "counts": counts}


def check_storage(mp3: Path) -> dict[str, object]:
    path = f"tracks/ws1_preflight_{uuid.uuid4().hex}/mix.mp3"
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    try:
        first = upload(str(mp3), path, "audio/mpeg")
        second = upload(str(mp3), path, "audio/mpeg")
        if first != second:
            raise RuntimeError("Upsert changed the public URL")
        with urlopen(second, timeout=30) as response:
            if response.headers.get_content_type() != "audio/mpeg" or response.read() != mp3.read_bytes():
                raise RuntimeError("Public audio bytes/content type differ from the uploaded MP3")
        samples, sr = load_mono(second)
        if sr != 44100 or not samples.size:
            raise RuntimeError("Public MP3 playback decode failed")
        return {"repeated_upload": True, "public_decode": True}
    finally:
        with client.storage as storage:
            storage.from_(BUCKET).remove([path])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Probe DB and upload/delete one synthetic storage object")
    args = parser.parse_args()
    report: dict[str, object] = {
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "librosa", "torch", "transformers", "psycopg", "pgvector", "supabase", "storage3")
        },
        "cuda": torch.cuda.is_available(),
        "mps": torch.backends.mps.is_available(),
    }
    failures = []
    with tempfile.TemporaryDirectory(prefix="beatopia-preflight-") as directory:
        wav, mp3 = Path(directory) / "source.wav", Path(directory) / "mix.mp3"
        samples = 0.25 * np.sin(2 * np.pi * 440 * np.arange(48000) / 48000)
        sf.write(wav, np.column_stack([samples, samples]), 48000)
        try:
            executable = shutil.which("ffmpeg")
            if executable is None:
                raise RuntimeError("FFmpeg missing")
            report["ffmpeg"] = subprocess.check_output([executable, "-version"], text=True).splitlines()[0]
            to_mp3(str(wav), str(mp3))
            info = sf.info(mp3)
            if info.samplerate != 44100 or info.channels != 2:
                raise RuntimeError("MP3 format differs from contract")
            decoded, sr = load_mono(str(mp3))
            if sr != 44100 or not 44000 <= len(decoded) <= 44200:
                raise RuntimeError("Audio roundtrip length differs")
            report["audio"] = {"sample_rate": info.samplerate, "channels": info.channels, "roundtrip": True}
        except Exception as error:
            report["audio"] = {"error_type": type(error).__name__}
            failures.append("audio")
        if args.live:
            try:
                report["database"] = check_database()
            except Exception as error:
                # Connection errors can contain credentials; emit types, never raw exceptions.
                report["database"] = {"error_type": type(error).__name__}
                failures.append("database")
            if "audio" not in failures:
                try:
                    report["storage"] = check_storage(mp3)
                except Exception as error:
                    report["storage"] = {"error_type": type(error).__name__}
                    failures.append("storage")
    report["failed_checks"] = failures
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
