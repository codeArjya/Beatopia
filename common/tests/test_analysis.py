from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from common import analysis
from common.analysis import TrackFeatures, analyze_track, make_windows, zero_shot_tags


@pytest.fixture(scope="module")
def fixture_audio() -> tuple[np.ndarray, int]:
    path = Path(__file__).resolve().parents[2] / "web/public/fixtures/audio/mix.wav"
    samples, sr = sf.read(path, dtype="float32", always_2d=True)
    return samples.mean(axis=1), sr


def test_fixture_tempo_windows_and_bounds(fixture_audio: tuple[np.ndarray, int]) -> None:
    y, sr = fixture_audio
    features = analyze_track(y, sr)
    assert features.duration_s == 16
    assert features.bpm == pytest.approx(90, abs=2)
    assert features.key == "A minor"
    assert len(features.beat_times) >= 8
    assert features.beat_times == sorted(set(features.beat_times))
    windows = make_windows(y, sr, features)
    assert [(window.start_s, window.end_s) for window in windows] == [(0, 10), (5, 15), (10, 16)]
    for window in windows:
        assert 0 <= window.loopability <= 1
        assert 0 <= window.density <= 1
        assert window.rms > 0.00562


def test_silence_and_empty_have_no_confident_features() -> None:
    for y in (np.zeros(0), np.zeros(44100 * 16), np.full(44100 * 4, 0.0001)):
        features = analyze_track(y, 44100)
        assert features.bpm is None
        assert features.key is None
        assert features.beat_times == []
        assert make_windows(y, 44100, features) == []


def test_short_window_is_not_padded_in_metadata() -> None:
    y = np.ones(44100 * 6, dtype=np.float32) * 0.1
    windows = make_windows(y, 44100, TrackFeatures(6, None, None, []))
    assert len(windows) == 1
    assert (windows[0].start_s, windows[0].end_s) == (0, 6)
    assert windows[0].loopability == 0
    assert make_windows(y[: 44100 * 3], 44100, TrackFeatures(3, None, None, [])) == []


@pytest.mark.parametrize("y", [np.array([np.nan]), np.array([np.inf]), np.zeros((2, 10))])
def test_rejects_invalid_audio(y: np.ndarray) -> None:
    with pytest.raises(ValueError, match="mono"):
        analyze_track(y, 44100)


@pytest.mark.parametrize("length,hop", [(0, 5), (10, 0), (float("nan"), 5), (10, -1)])
def test_rejects_invalid_window_parameters(length: float, hop: float) -> None:
    with pytest.raises(ValueError):
        make_windows(np.zeros(44100), 44100, TrackFeatures(1, None, None, []), length, hop)


def test_tags_use_per_category_threshold_and_store_every_score(monkeypatch: pytest.MonkeyPatch) -> None:
    categories = {category: [f"{category}{i}" for i in range(30)] for category in ("instrument", "genre", "mood")}
    monkeypatch.setattr(analysis, "_vocab", lambda: categories)
    text = np.zeros((90, 512), dtype=np.float32)
    text[:, 0] = np.tile([0.9, 0.8, 0.7] + [0.1] * 27, 3)
    text[:, 1] = np.sqrt(1 - text[:, 0] ** 2)
    monkeypatch.setattr(analysis, "_tag_embeddings", lambda tags: text)
    audio = np.zeros((1, 512), dtype=np.float32)
    audio[0, 0] = 2  # Input normalization must make these true cosine similarities.
    tags, scores = zero_shot_tags(audio)[0]
    assert tags == [f"{category}{i}" for category in categories for i in range(3)]
    assert len(scores) == 90
    assert scores["instrument0"] == pytest.approx(0.9)
    assert scores["mood29"] == pytest.approx(0.1)


def test_tagging_empty_and_invalid_embeddings() -> None:
    assert zero_shot_tags(np.empty((0, 512))) == []
    for vectors in (np.zeros((1, 512)), np.zeros((1, 511)), np.full((1, 512), np.nan)):
        with pytest.raises(ValueError):
            zero_shot_tags(vectors)
