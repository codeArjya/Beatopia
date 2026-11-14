from types import SimpleNamespace

import numpy as np
import pytest

from common import clap


def test_empty_embeddings_do_not_load_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected() -> None:
        raise AssertionError("Model should not load")

    monkeypatch.setattr(clap, "_runtime", unexpected)
    for result in (clap.embed_audio([], 44100), clap.embed_text([])):
        assert result.shape == (0, 512)
        assert result.dtype == np.float32


def test_audio_is_resampled_once_and_truncated_deterministically(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = []

    def capture(items: list[np.ndarray], *, audio: bool) -> np.ndarray:
        assert audio
        captured.extend(items)
        return np.ones((len(items), 512), dtype=np.float32)

    monkeypatch.setattr(clap, "_embed", capture)
    clap.embed_audio([np.ones(44100 * 12), np.zeros(44100 * 4)], 44100)
    assert [len(chunk) for chunk in captured] == [480000, 192000]
    assert all(chunk.dtype == np.float32 for chunk in captured)
    assert np.mean(captured[0]) == pytest.approx(1, abs=0.001)


@pytest.mark.parametrize("chunk", [np.zeros(0), np.zeros((2, 100)), np.array([np.nan])])
def test_invalid_audio_rejected_before_loading(chunk: np.ndarray) -> None:
    with pytest.raises(ValueError):
        clap.embed_audio([chunk], 44100)


def test_invalid_text_rejected_before_loading() -> None:
    with pytest.raises(ValueError):
        clap.embed_text([" "])


def test_oom_reduces_batch_without_losing_order(monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    attempted = []

    class Batch(dict):
        def to(self, device: torch.device) -> "Batch":
            return self

    def tokenize(items: list[str], **kwargs: object) -> Batch:
        return Batch(indices=[int(item) for item in items])

    def features(indices: list[int]) -> SimpleNamespace:
        attempted.append(len(indices))
        if len(indices) > 2:
            raise torch.OutOfMemoryError("synthetic OOM")
        tensor = torch.zeros((len(indices), 512))
        for row, index in enumerate(indices):
            tensor[row, index] = 2
        return SimpleNamespace(pooler_output=tensor)

    model = SimpleNamespace(device=torch.device("cpu"), get_text_features=features)
    processor = SimpleNamespace(tokenizer=tokenize)
    monkeypatch.setattr(clap, "_runtime", lambda: (model, processor))
    result = clap.embed_text([str(index) for index in range(17)])
    assert attempted[:4] == [16, 8, 4, 2]
    assert result.shape == (17, 512)
    np.testing.assert_array_equal(result.argmax(axis=1), np.arange(17))
    np.testing.assert_allclose(np.linalg.norm(result, axis=1), 1)
