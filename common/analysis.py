"""Track and window analysis, used by ingest AND by the worker's 'analyze' job (CONTRACT §4)."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import librosa
import numpy as np

from common.clap import embed_text


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


def _validate_audio(y: np.ndarray, sr: int) -> np.ndarray:
    if isinstance(sr, bool) or not isinstance(sr, int) or sr <= 0:
        raise ValueError("Sample rate must be a positive integer")
    samples = np.asarray(y, dtype=np.float32)
    if samples.ndim != 1 or not np.isfinite(samples).all():
        raise ValueError("Analysis requires finite mono samples")
    return samples


def _key(y: np.ndarray, sr: int) -> str | None:
    if len(y) < sr * 2:
        return None
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    chroma -= chroma.mean()
    norm = np.linalg.norm(chroma)
    if norm < 1e-8:
        return None
    # Krumhansl-Kessler pitch-class profiles used for K-S template matching.
    profiles = {
        "major": [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
        "minor": [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    }
    notes = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    best_score, best_key = -np.inf, None
    for mode, values in profiles.items():
        profile = np.asarray(values)
        profile -= profile.mean()
        profile /= np.linalg.norm(profile)
        for pitch, name in enumerate(notes):
            score = float(chroma @ np.roll(profile, pitch) / norm)
            if score > best_score:
                best_score, best_key = score, f"{name} {mode}"
    return best_key


def analyze_track(y: np.ndarray, sr: int) -> TrackFeatures:
    y = _validate_audio(y, sr)
    duration = len(y) / sr
    if len(y) == 0 or np.sqrt(np.mean(y.astype(np.float64) ** 2)) < 10 ** (-45 / 20):
        return TrackFeatures(duration, None, None, [])
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    beat_times = np.asarray(beats, dtype=np.float64)
    beat_times = np.unique(beat_times[np.isfinite(beat_times) & (beat_times >= 0) & (beat_times < duration)])
    tempo_values = np.asarray(tempo).reshape(-1)
    bpm = float(tempo_values[0]) if tempo_values.size else float("nan")
    intervals = np.diff(beat_times)
    if (
        len(beat_times) < 8
        or not np.isfinite(bpm)
        or bpm <= 0
        or intervals.mean() <= 0
        or intervals.std() / intervals.mean() > 0.20
    ):
        bpm = None
    return TrackFeatures(duration, bpm, _key(y, sr), beat_times.tolist())


def _loopability(onsets: np.ndarray, sr: int, beats: np.ndarray) -> float:
    if len(beats) < 9:
        return 0.0
    times = librosa.frames_to_time(np.arange(len(onsets)), sr=sr)
    bars = [
        np.interp(np.linspace(beats[i], beats[i + 4], 64, endpoint=False), times, onsets)
        for i in range(0, len(beats) - 4, 4)
    ]
    similarities = []
    for previous, current in zip(bars, bars[1:], strict=False):
        denominator = np.linalg.norm(previous) * np.linalg.norm(current)
        similarities.append(float(previous @ current / denominator) if denominator > 0 else 0.0)
    return float(np.clip(np.mean(similarities), 0, 1)) if similarities else 0.0


def make_windows(
    y: np.ndarray, sr: int, feats: TrackFeatures, length_s: float = 10.0, hop_s: float = 5.0
) -> list[WindowFeatures]:
    y = _validate_audio(y, sr)
    if not np.isfinite([length_s, hop_s]).all() or length_s <= 0 or hop_s <= 0:
        raise ValueError("Window length and hop must be finite and positive")
    length, hop = round(length_s * sr), round(hop_s * sr)
    if min(length, hop) < 1:
        raise ValueError("Window length and hop must cover at least one sample")
    if len(y) < min(length, 4 * sr):
        return []
    onsets = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.onset.onset_detect(onset_envelope=onsets, sr=sr, units="time")
    flatness = librosa.feature.spectral_flatness(y=y)[0]
    flat_times = librosa.frames_to_time(np.arange(len(flatness)), sr=sr)
    beats = np.asarray(feats.beat_times)
    windows = []
    for start in range(0, len(y), hop):
        end = min(start + length, len(y))
        if end - start < min(length, 4 * sr):
            break
        chunk = y[start:end]
        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        start_s, end_s = start / sr, end / sr
        if rms >= 10 ** (-45 / 20):
            selected = flatness[(flat_times >= start_s) & (flat_times < end_s)]
            spectral = float(selected.mean()) if selected.size else 0.0
            rate = np.count_nonzero((onset_times >= start_s) & (onset_times < end_s)) / (end_s - start_s)
            density = float(np.clip((spectral + min(rate / 10, 1)) / 2, 0, 1))
            window_beats = beats[(beats >= start_s) & (beats <= end_s)]
            loopability = _loopability(onsets, sr, window_beats) if feats.bpm is not None else 0.0
            windows.append(WindowFeatures(start_s, end_s, loopability, rms, density))
        if end == len(y):
            break
    return windows


def _vocab() -> dict[str, list[str]]:
    path = Path(__file__).resolve().parents[1] / "ingest" / "vocab.txt"
    categories: dict[str, list[str]] = {"instrument": [], "genre": [], "mood": []}
    category = None
    for line in path.read_text(encoding="utf-8").splitlines():
        tag = line.strip()
        if tag.startswith("#"):
            heading = tag.lstrip("#").strip()
            if heading in categories:
                category = heading
        elif tag and category is not None:
            categories[category].append(tag)
    tags = [tag for group in categories.values() for tag in group]
    if not all(categories.values()) or len(tags) != len(set(tags)):
        raise ValueError("Vocabulary must contain three nonempty categories and unique tags")
    return categories


@lru_cache(maxsize=1)
def _tag_embeddings(tags: tuple[str, ...]) -> np.ndarray:
    return embed_text([f"a recording of {tag}" for tag in tags])


def zero_shot_tags(embeddings: np.ndarray) -> list[tuple[list[str], dict[str, float]]]:
    """For each embedding, return (kept tags, {tag: similarity for every vocab tag}). Uses ingest/vocab.txt."""
    vectors = np.asarray(embeddings, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[1] != 512 or not np.isfinite(vectors).all():
        raise ValueError("Tagging requires finite (n, 512) embeddings")
    if len(vectors) == 0:
        return []
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("Tagging requires nonzero embeddings")
    categories = _vocab()
    tags = tuple(tag for group in categories.values() for tag in group)
    scores = np.clip((vectors / norms) @ _tag_embeddings(tags).T, -1, 1)
    output = []
    for row in scores:
        kept, offset = [], 0
        for group in categories.values():
            values = row[offset : offset + len(group)]
            threshold = values.mean() + values.std()
            order = np.argsort(-values, kind="stable")
            kept.extend(group[index] for index in order[:3] if values[index] > threshold)
            offset += len(group)
        output.append((kept, {tag: float(value) for tag, value in zip(tags, row, strict=True)}))
    return output
