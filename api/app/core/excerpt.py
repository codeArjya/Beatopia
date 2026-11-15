"""Short MP3 excerpt of a window for the audio `/why` note (PLAN §1 "Why notes with audio").

ffmpeg seeks into the public MP3 over HTTP (range requests, so only the excerpt is downloaded) and re-encodes it
as mono 64 kbps MP3: a 15 s excerpt is ≈ 120 KB, far below Gemini's inline-data limit. Measured on the dev bucket:
≈ 1.9 s for 15 s. Any failure raises `ExcerptError`, and the caller falls back to the text-only prompt (P3b).
"""

from __future__ import annotations

import shutil
import subprocess

MAX_EXCERPT_S = 15.0
SAMPLE_RATE = 22_050
BITRATE = "64k"
TIMEOUT_S = 10.0
MIN_BYTES = 1_000  # anything smaller is not a usable excerpt (empty or near-empty decode)
PROTOCOLS = "file,http,https,tcp,tls,crypto"


class ExcerptError(Exception):
    """The excerpt could not be cut (no ffmpeg, network, decode error, timeout)."""


def cut_excerpt(source: str, start_s: float, duration_s: float) -> bytes:
    """MP3 bytes of `source` (URL or local path) from `start_s` for `duration_s` (capped at 15 s)."""
    duration_s = min(duration_s, MAX_EXCERPT_S)
    if duration_s <= 0:
        raise ExcerptError("empty excerpt range")
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise ExcerptError("ffmpeg is not installed")
    args = [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-protocol_whitelist",
        PROTOCOLS,
        "-ss",
        f"{max(start_s, 0.0):.3f}",
        "-t",
        f"{duration_s:.3f}",
        "-i",
        source,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "libmp3lame",
        "-b:a",
        BITRATE,
        "-f",
        "mp3",
        "pipe:1",
    ]
    try:
        result = subprocess.run(args, capture_output=True, timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ExcerptError(f"ffmpeg took longer than {TIMEOUT_S:.0f} s") from exc
    except OSError as exc:
        raise ExcerptError(f"ffmpeg could not start: {exc}") from exc
    if result.returncode != 0:
        # stderr can contain the URL; keep it out of the error text that may reach logs verbatim.
        raise ExcerptError(f"ffmpeg exited with {result.returncode}")
    if len(result.stdout) < MIN_BYTES:
        raise ExcerptError("ffmpeg produced no audio")
    return result.stdout
