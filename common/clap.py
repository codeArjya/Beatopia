"""CLAP embeddings: the SAME model at ingest and at query time (CONTRACT §4).

Only this module touches CLAP. It resamples to 48 kHz internally; callers pass audio at any rate.
"""

import os
from functools import lru_cache
from threading import RLock
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from transformers import ClapModel, ClapProcessor

CLAP_MODEL = os.environ.get("CLAP_MODEL", "laion/larger_clap_music")
# The same immutable checkpoint is used by ingest, worker, and query embedding.
CLAP_REVISION = os.environ.get(
    "CLAP_REVISION", "a0b4534a14f58e20944452dff00a22a06ce629d1" if CLAP_MODEL == "laion/larger_clap_music" else "main"
)
_MODEL_LOCK = RLock()


@lru_cache(maxsize=1)
def _runtime() -> tuple["ClapModel", "ClapProcessor"]:
    import torch
    from transformers import ClapModel, ClapProcessor

    processor = ClapProcessor.from_pretrained(CLAP_MODEL, revision=CLAP_REVISION)
    model = ClapModel.from_pretrained(CLAP_MODEL, revision=CLAP_REVISION)
    if model.config.projection_dim != 512:
        raise ValueError("CLAP checkpoint must have 512-dimensional projections")
    if processor.feature_extractor.sampling_rate != 48000:
        raise ValueError("CLAP checkpoint must accept 48 kHz audio")
    model.eval().to("cuda" if torch.cuda.is_available() else "cpu")
    return model, processor


def _embed(items: list[np.ndarray] | list[str], *, audio: bool) -> np.ndarray:
    import torch

    outputs = []
    batch_size, offset = 16, 0
    # Concurrent API requests share weights and cannot exhaust device memory together.
    with _MODEL_LOCK, torch.inference_mode():
        model, processor = _runtime()
        while offset < len(items):
            batch = items[offset : offset + batch_size]
            inputs = result = None
            try:
                if audio:
                    inputs = processor.feature_extractor(
                        batch, sampling_rate=48000, padding="pad", truncation="rand_trunc", return_tensors="pt"
                    ).to(model.device)
                    result = model.get_audio_features(**inputs).pooler_output
                else:
                    inputs = processor.tokenizer(batch, padding=True, truncation=True, return_tensors="pt").to(
                        model.device
                    )
                    result = model.get_text_features(**inputs).pooler_output
                vectors = result.detach().float().cpu().numpy()
                if vectors.shape != (len(batch), 512) or not np.isfinite(vectors).all():
                    raise RuntimeError("CLAP returned invalid projected embeddings")
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                if np.any(norms <= 0):
                    raise RuntimeError("CLAP returned a zero embedding")
                outputs.append((vectors / norms).astype(np.float32))
                offset += len(batch)
            except torch.OutOfMemoryError:
                inputs = result = None
                if batch_size > 1:
                    batch_size = max(1, batch_size // 2)
                elif model.device.type != "cpu":
                    model.to("cpu")
                else:
                    raise
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
    return np.concatenate(outputs)


def embed_audio(chunks: list[np.ndarray], sr: int) -> np.ndarray:
    """Return an (n, 512) float32 array of L2-normalized audio embeddings. Resamples to 48 kHz."""
    import librosa

    if isinstance(sr, bool) or not isinstance(sr, int) or sr <= 0:
        raise ValueError("Sample rate must be a positive integer")
    if not chunks:
        return np.empty((0, 512), dtype=np.float32)
    prepared = []
    for chunk in chunks:
        y = np.asarray(chunk, dtype=np.float32)
        if y.ndim != 1 or y.size == 0 or not np.isfinite(y).all():
            raise ValueError("CLAP chunks must be nonempty, finite mono arrays")
        # Windows are at most 10 seconds. Longer callers get a deterministic first window.
        y = y[: sr * 10]
        target_samples = round(len(y) * 48000 / sr)
        if sr != 48000:
            y = librosa.resample(y, orig_sr=sr, target_sr=48000)
        prepared.append(y[:target_samples])
    return _embed(prepared, audio=True)


def embed_text(texts: list[str]) -> np.ndarray:
    """Return an (n, 512) float32 array of L2-normalized text embeddings."""
    if not texts:
        return np.empty((0, 512), dtype=np.float32)
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("CLAP texts must be nonempty strings")
    return _embed(texts, audio=False)
