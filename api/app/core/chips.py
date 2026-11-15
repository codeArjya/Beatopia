"""Chips (CONTRACT §6 `GET /chips`): tag chips from `ingest/vocab.txt` plus fixed tempo and key chips."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import Literal

from app.models.api import Chip, ChipCategory, ChipFilter, ChipsResponse

CategoryId = Literal["instrument", "genre", "mood", "tempo", "key"]
TAG_CATEGORIES: dict[str, tuple[CategoryId, str, str]] = {
    # vocab header → (category id, chip id prefix, category label)
    "instrument": ("instrument", "inst", "Instruments"),
    "genre": ("genre", "genre", "Genres"),
    "mood": ("mood", "mood", "Moods"),
}
LABEL_OVERRIDES = {"r&b": "R&B"}

TEMPOS = range(70, 161, 10)
TEMPO_HALF_WIDTH = 5
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]  # sharps only, like tracks.key
KEYS = [f"{n} {mode}" for mode in ("major", "minor") for n in NOTES]


def slug(text: str) -> str:
    """`synth pad` → `synth_pad`, `hi-hats` → `hi_hats`, `r&b` → `rnb`, `C# minor` → `c_sharp_minor`."""
    s = text.lower().replace("&", "n").replace("#", "_sharp")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def label(tag: str) -> str:
    return LABEL_OVERRIDES.get(tag, tag[:1].upper() + tag[1:])


def parse_vocab(path: Path) -> dict[str, list[str]]:
    """Tags grouped by their `# <category>` header. Other comment lines and blank lines are ignored."""
    groups: dict[str, list[str]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            header = line.lstrip("#").strip().lower()
            if header in TAG_CATEGORIES:
                current = header
                groups.setdefault(current, [])
            continue
        if current is None:
            raise ValueError(f"{path}: tag {line!r} appears before any category header")
        if line not in groups[current]:
            groups[current].append(line)
    missing = set(TAG_CATEGORIES) - set(groups)
    if missing:
        raise ValueError(f"{path}: missing category headers {sorted(missing)}")
    return groups


def build_chips(vocab: dict[str, list[str]]) -> ChipsResponse:
    categories: list[ChipCategory] = []
    for header, (cat_id, prefix, cat_label) in TAG_CATEGORIES.items():
        chips = [
            Chip(id=f"{prefix}.{slug(tag)}", label=label(tag), category=cat_id, filter=ChipFilter(tags=[tag]))
            for tag in vocab[header]
        ]
        categories.append(ChipCategory(id=cat_id, label=cat_label, color=f"--chip-{cat_id}", chips=chips))

    tempo = [
        Chip(
            id=f"tempo.{bpm}",
            label=f"{bpm} BPM",
            category="tempo",
            filter=ChipFilter(bpm_range=(bpm - TEMPO_HALF_WIDTH, bpm + TEMPO_HALF_WIDTH)),
        )
        for bpm in TEMPOS
    ]
    categories.append(ChipCategory(id="tempo", label="Tempo", color="--chip-tempo", chips=tempo))

    keys = [Chip(id=f"key.{slug(k)}", label=k, category="key", filter=ChipFilter(key=k)) for k in KEYS]
    categories.append(ChipCategory(id="key", label="Key", color="--chip-key", chips=keys))

    ids = [c.id for cat in categories for c in cat.chips]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicate chip ids from vocab: {dupes}")
    return ChipsResponse(categories=categories)


@cache
def load_chips(vocab_path: Path) -> ChipsResponse:
    return build_chips(parse_vocab(vocab_path))


@cache
def chip_index(vocab_path: Path) -> dict[str, Chip]:
    """Chip id → Chip, for merging chip filters into a SearchPlan (T4.1)."""
    return {c.id: c for cat in load_chips(vocab_path).categories for c in cat.chips}


def all_tags(vocab_path: Path) -> list[str]:
    return [tag for tags in parse_vocab(vocab_path).values() for tag in tags]
