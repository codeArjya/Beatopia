"""Audio I/O helpers (CONTRACT §4)."""

import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

import numpy as np
import soundfile as sf


def _ffmpeg(arguments: list[str]) -> bytes:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("FFmpeg is required; install it and add its bin directory to PATH")
    try:
        result = subprocess.run(
            [executable, "-hide_banner", "-loglevel", "error", "-nostdin", *arguments],
            capture_output=True,
            check=True,
            timeout=300,
        )
    except subprocess.CalledProcessError:
        # Diagnostics may contain signed URLs or other private input metadata.
        raise ValueError("FFmpeg could not process the audio; check the file and codec") from None
    except subprocess.TimeoutExpired:
        raise TimeoutError("FFmpeg audio processing exceeded 300 seconds") from None
    return result.stdout


def _decode_mono(path: Path, sr: int) -> np.ndarray:
    if not path.is_file():
        raise FileNotFoundError(path)
    raw = _ffmpeg(
        [
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(path.resolve()),
            "-map",
            "0:a:0",
            "-vn",
            "-ar",
            str(sr),
            "-c:a",
            "pcm_f32le",
            "-f",
            "wav",
            "pipe:1",
        ]
    )
    # Preserve channels during decoding, then average without a remix-matrix gain.
    channels, _ = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    samples = channels.mean(axis=1)
    if samples.size == 0 or not np.isfinite(samples).all():
        raise ValueError("Audio must contain finite, nonempty samples")
    return samples


def load_mono(path_or_url: str, sr: int = 44100) -> tuple[np.ndarray, int]:
    """Load a local file or URL as mono float32 at `sr`. Returns (samples, sr)."""
    if isinstance(sr, bool) or not isinstance(sr, int) or sr <= 0:
        raise ValueError("Sample rate must be a positive integer")
    if urlsplit(path_or_url).scheme.lower() in {"http", "https"}:
        # Download first: no network protocols are enabled inside the decoder.
        with tempfile.TemporaryDirectory(prefix="beatopia-audio-") as directory:
            local = Path(directory) / "input.audio"
            with urlopen(path_or_url, timeout=30) as response, local.open("wb") as output:
                shutil.copyfileobj(response, output)
            return _decode_mono(local, sr), sr
    return _decode_mono(Path(path_or_url), sr), sr


def to_mp3(src_path: str, dst_path: str, bitrate: str = "192k") -> None:
    """Transcode `src_path` to a 44.1 kHz stereo MP3 with ffmpeg."""
    source, destination = Path(src_path).resolve(), Path(dst_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == destination:
        raise ValueError("Source and destination must differ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Failed transcodes never replace a valid cached mix.
    with tempfile.TemporaryDirectory(prefix=".encode-", dir=destination.parent) as directory:
        temporary = Path(directory) / "mix.mp3"
        _ffmpeg(
            [
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-map_metadata",
                "-1",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-c:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                "-y",
                str(temporary),
            ]
        )
        if temporary.stat().st_size == 0:
            raise ValueError("FFmpeg produced an empty MP3")
        temporary.replace(destination)
