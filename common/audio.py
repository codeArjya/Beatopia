"""Audio I/O helpers (CONTRACT §4)."""

import numpy as np


def load_mono(path_or_url: str, sr: int = 44100) -> tuple[np.ndarray, int]:
    """Load a local file or URL as mono float32 at `sr`. Returns (samples, sr)."""
    raise NotImplementedError("WS1: common.audio.load_mono")


def to_mp3(src_path: str, dst_path: str, bitrate: str = "192k") -> None:
    """Transcode `src_path` to a 44.1 kHz stereo MP3 with ffmpeg."""
    raise NotImplementedError("WS1: common.audio.to_mp3")
