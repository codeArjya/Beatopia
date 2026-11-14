"""Track and window analysis, used by ingest AND by the worker's 'analyze' job (CONTRACT §4)."""

from dataclasses import dataclass

import numpy as np


@dataclass
class WindowFeatures:
    start_s: float
    end_s: float
    loopability: float
    rms: float
    density: float


@dataclass
class TrackFeatures:
    duration_s: float
    bpm: float | None
    key: str | None
    beat_times: list[float]


def analyze_track(y: np.ndarray, sr: int) -> TrackFeatures:
    raise NotImplementedError("WS1: common.analysis.analyze_track")


def make_windows(
    y: np.ndarray, sr: int, feats: TrackFeatures, length_s: float = 10.0, hop_s: float = 5.0
) -> list[WindowFeatures]:
    raise NotImplementedError("WS1: common.analysis.make_windows")


def zero_shot_tags(embeddings: np.ndarray) -> list[tuple[list[str], dict[str, float]]]:
    """For each embedding, return (kept tags, {tag: similarity for every vocab tag}). Uses ingest/vocab.txt."""
    raise NotImplementedError("WS1: common.analysis.zero_shot_tags")
