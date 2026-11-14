"""ID helpers (CONTRACT §2)."""


def window_id(track_id: str, stem: str, start_s: float) -> str:
    """`{track_id}:{stem}:{start_ms}`, e.g. window_id("fs_482913", "mix", 15.0) == "fs_482913:mix:15000"."""
    if start_s < 0:
        raise ValueError(f"start_s must be >= 0, got {start_s}")
    return f"{track_id}:{stem}:{round(start_s * 1000)}"
