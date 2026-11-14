"""ID helpers (CONTRACT §2)."""

import math


def window_id(track_id: str, stem: str, start_s: float) -> str:
    """`{track_id}:{stem}:{start_ms}`, e.g. window_id("fs_482913", "mix", 15.0) == "fs_482913:mix:15000"."""
    if not math.isfinite(start_s) or start_s < 0:
        raise ValueError("start_s must be finite and >= 0")
    return f"{track_id}:{stem}:{round(start_s * 1000)}"
