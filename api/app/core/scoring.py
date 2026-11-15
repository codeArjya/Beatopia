"""Search scoring (CONTRACT §7.4) and result diversity (§7.5): weights, per-track cap, overlap dedupe."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.core.search_sql import Candidate
from app.models.api import SearchPlan

# §7.4 weights: score = 0.6·sim + 0.2·tag_overlap + 0.1·bpm_fit + 0.1·loopability (− 0.15·density if prefer_sparse)
W_SIM = 0.6
W_TAGS = 0.2
W_BPM = 0.1
W_LOOP = 0.1
SPARSE_PENALTY = 0.15

TAG_OVERLAP_NO_MUST = 0.5  # tag_overlap when the plan has no must_tags
BPM_FIT_UNKNOWN = 0.5  # bpm_fit when the track bpm is null
BPM_FALLOFF = 10.0  # bpm_fit falls linearly from 1 to 0 over this many bpm outside the range

MAX_PER_TRACK = 3  # §7.5
DEDUPE_OVERLAP = 0.5  # same track + stem windows overlapping at least this share of the shorter one are dropped


def clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def similarity(distance: float) -> float:
    """pgvector cosine distance (`<=>`, 0..2) → similarity clamped to 0..1."""
    return clamp01(1.0 - distance)


def tag_overlap(must: Sequence[str], tags: Iterable[str]) -> float:
    if not must:
        return TAG_OVERLAP_NO_MUST
    return len(set(must) & set(tags)) / len(set(must))


def bpm_fit(bpm: float | None, bpm_range: tuple[float, float] | None) -> float:
    if bpm_range is None:
        return 1.0
    if bpm is None:
        return BPM_FIT_UNKNOWN
    lo, hi = sorted(bpm_range)
    outside = min(max(lo - b, b - hi, 0.0) for b in (bpm, bpm * 2, bpm / 2))  # half/double time counts as a fit
    return clamp01(1.0 - outside / BPM_FALLOFF)


def score(c: Candidate, plan: SearchPlan) -> float:
    s = (
        W_SIM * similarity(c.distance)
        + W_TAGS * tag_overlap(plan.must_tags, c.tags)
        + W_BPM * bpm_fit(c.bpm, plan.bpm_range)
        + W_LOOP * c.loopability
    )
    if plan.prefer_sparse:
        s -= SPARSE_PENALTY * c.density
    return clamp01(s)


@dataclass(frozen=True)
class Scored:
    candidate: Candidate
    score: float


def overlap_share(a: Candidate, b: Candidate) -> float:
    """Overlap of two windows as a share of the shorter one (0 when they don't touch)."""
    inter = min(a.end_s, b.end_s) - max(a.start_s, b.start_s)
    shorter = min(a.end_s - a.start_s, b.end_s - b.start_s)
    return max(0.0, inter) / shorter if shorter > 0 else 0.0


def rank(candidates: Iterable[Candidate], plan: SearchPlan) -> list[Scored]:
    """Score, sort best first, drop near-duplicate windows, keep at most MAX_PER_TRACK per track."""
    scored = sorted(
        (Scored(c, score(c, plan)) for c in candidates),
        key=lambda s: (-s.score, s.candidate.distance, s.candidate.window_id),
    )
    kept: list[Scored] = []
    per_track: dict[str, list[Candidate]] = defaultdict(list)
    for s in scored:
        same_track = per_track[s.candidate.track_id]
        if len(same_track) >= MAX_PER_TRACK:
            continue
        if any(o.stem == s.candidate.stem and overlap_share(o, s.candidate) >= DEDUPE_OVERLAP for o in same_track):
            continue
        same_track.append(s.candidate)
        kept.append(s)
    return kept
