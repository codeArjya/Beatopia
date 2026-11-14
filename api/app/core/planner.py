"""SearchPlan building (CONTRACT §7.1). Chips are merged deterministically after the plan, so chips always apply.

v1 (T3.2) has no Gemini: the plan is the raw text, or the chip labels. T4.1 adds the Gemini planner + plan_cache in
front of `merge_chips`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.core.chips import chip_index
from app.core.errors import bad_request
from app.models.api import Chip, SearchPlan

CAPTION_CATEGORIES = ("instrument", "genre", "mood")  # tempo/key chips never go into the CLAP caption
GENERIC_CAPTION = "music"


def normalize_text(text: str | None) -> str | None:
    text = " ".join((text or "").split())
    return text or None


def resolve_chips(chip_ids: Sequence[str], vocab_path: Path) -> list[Chip]:
    index = chip_index(vocab_path)
    unknown = [c for c in chip_ids if c not in index]
    if unknown:
        raise bad_request(f"unknown chip id(s): {', '.join(unknown)} (use the ids from GET /chips)")
    return [index[c] for c in chip_ids]


def chip_caption(chips: Sequence[Chip]) -> str:
    """'trumpet, soul, melancholy music' from the instrument/genre/mood chips; 'music' if there are none."""
    labels = [c.label.lower() for c in chips if c.category in CAPTION_CATEGORIES]
    return f"{', '.join(labels)} {GENERIC_CAPTION}" if labels else GENERIC_CAPTION


def base_plan(text: str | None, chips: Sequence[Chip]) -> SearchPlan:
    """The plan without Gemini (also the fallback when Gemini fails): CLAP caption only, no filters."""
    return SearchPlan(clap_text=text or chip_caption(chips))


def merge_chips(plan: SearchPlan, chips: Sequence[Chip]) -> SearchPlan:
    """Chip tags → must_tags (and out of exclude_tags); tempo chips → min(lo)..max(hi); last key chip wins."""
    chip_tags = [t for c in chips for t in c.filter.tags]
    must = list(dict.fromkeys([*plan.must_tags, *chip_tags]))
    exclude = [t for t in plan.exclude_tags if t not in set(chip_tags)]
    ranges = [c.filter.bpm_range for c in chips if c.filter.bpm_range is not None]
    bpm_range = (min(lo for lo, _ in ranges), max(hi for _, hi in ranges)) if ranges else plan.bpm_range
    keys = [c.filter.key for c in chips if c.filter.key]
    return plan.model_copy(
        update={
            "must_tags": must,
            "exclude_tags": exclude,
            "bpm_range": bpm_range,
            "key": keys[-1] if keys else plan.key,
        }
    )
