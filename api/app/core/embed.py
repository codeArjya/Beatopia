"""Query-time CLAP (common.clap, the same model and revision as ingest). Loaded and warmed once in the lifespan."""

from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

from common import clap

log = logging.getLogger("app.embed")

QUERY_CACHE_SIZE = 512


def warm() -> bool:
    """Load the model by embedding one dummy string. False while WS1's `embed_text` is still a stub."""
    try:
        clap.embed_text(["warmup"])
    except NotImplementedError:
        log.warning("common.clap.embed_text is not implemented yet (WS1); /search needs it")
        return False
    log.info("clap warm (%s @ %s)", clap.CLAP_MODEL, getattr(clap, "CLAP_REVISION", "main"))
    return True


@lru_cache(maxsize=QUERY_CACHE_SIZE)
def embed_query(text: str) -> np.ndarray:
    """One L2-normalized 512-d text vector, LRU-cached by text. The returned array is read-only (shared)."""
    vec = clap.embed_text([text])[0].astype(np.float32)
    vec.setflags(write=False)
    return vec
