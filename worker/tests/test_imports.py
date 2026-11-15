from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from common import analysis
from worker import imports


@pytest.fixture
def original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    sr = 44100
    t = np.arange(16 * sr) / sr
    path = tmp_path / "original.wav"
    sf.write(path, 0.2 * np.sin(2 * np.pi * 440 * t), sr)
    monkeypatch.setattr(analysis, "analyze_track", lambda y, sr: analysis.TrackFeatures(len(y) / sr, None, None, []))

    def embed(chunks: list[np.ndarray], sr: int) -> np.ndarray:
        vectors = np.zeros((len(chunks), 512), dtype=np.float32)
        vectors[:, 0] = 1
        return vectors

    monkeypatch.setattr(imports.clap, "embed_audio", embed)
    monkeypatch.setattr(analysis, "zero_shot_tags", lambda e: [(["tone"], {"tone": 0.4}) for _ in e])
    return path, "imp_1234abcd"


def test_prepare_playable_windows_and_resume(original: tuple[Path, str], tmp_path: Path) -> None:
    path, tid = original
    manifest, vectors = imports.prepare(tid, path, tmp_path, {})
    assert manifest["duration_s"] == 16
    assert [(w["start_s"], w["end_s"]) for w in manifest["windows"]] == [(0, 10), (5, 15), (10, 16)]
    assert vectors.shape == (3, 512) and np.allclose(np.linalg.norm(vectors, axis=1), 1)
    info = sf.info(tmp_path / "mix.mp3")
    assert info.samplerate == 44100 and info.channels == 2
    timings: dict = {}
    again, actual = imports.prepare(tid, path, tmp_path, timings)
    assert again == manifest and np.array_equal(actual, vectors) and timings["analysis_reused"]
    np.savez_compressed(tmp_path / "features.npz", embeddings=vectors * 2)
    repaired, actual = imports.prepare(tid, path, tmp_path, {})
    assert repaired == manifest and np.array_equal(actual, vectors)


def test_changed_identity_and_silence_are_not_faked(original: tuple[Path, str], tmp_path: Path) -> None:
    path, tid = original
    imports.prepare(tid, path, tmp_path, {})
    sf.write(path, np.zeros(44100 * 16), 44100)
    with pytest.raises(ValueError, match="identity changed"):
        imports.prepare(tid, path, tmp_path, {})
    empty = tmp_path / "silent"
    empty.mkdir()
    with pytest.raises(ValueError, match="no audible searchable windows"):
        imports.prepare(tid, path, empty, {})


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"track_id": "fs_1", "path": "imports/fs_1/original.wav"},
        {"track_id": "imp_a", "path": "imports/imp_b/original.wav"},
        {"track_id": "imp_a", "path": "imports/imp_a/../../original.wav"},
        {"track_id": "imp_a", "path": "https://example.com/original.wav"},
    ],
)
def test_malformed_import_input_fails_before_db(data: object, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        imports.analyze(data, tmp_path, lambda _: None, {})
