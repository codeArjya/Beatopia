"""CLAP embeddings: the SAME model at ingest and at query time (CONTRACT §4).

Only this module touches CLAP. It resamples to 48 kHz internally; callers pass audio at any rate.
"""

import os

import numpy as np

CLAP_MODEL = os.environ.get("CLAP_MODEL", "laion/larger_clap_music")


def embed_audio(chunks: list[np.ndarray], sr: int) -> np.ndarray:
    """Return an (n, 512) float32 array of L2-normalized audio embeddings. Resamples to 48 kHz."""
    raise NotImplementedError("WS1: common.clap.embed_audio")


def embed_text(texts: list[str]) -> np.ndarray:
    """Return an (n, 512) float32 array of L2-normalized text embeddings."""
    raise NotImplementedError("WS1: common.clap.embed_text")
