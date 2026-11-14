"""Query-time CLAP (common.clap, the same model as ingest). Loaded and warmed once in the lifespan."""

from __future__ import annotations

import logging

from common import clap

log = logging.getLogger("app.embed")


def warm() -> bool:
    """Load the model by embedding one dummy string. False while WS1's `embed_text` is still a stub."""
    try:
        clap.embed_text(["warmup"])
    except NotImplementedError:
        log.warning("common.clap.embed_text is not implemented yet (WS1); /search needs it")
        return False
    log.info("clap warm (%s)", clap.CLAP_MODEL)
    return True
