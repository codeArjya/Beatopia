"""T3.1: score math (CONTRACT §7.4) and diversity rules (§7.5)."""

from typing import Any

import pytest

from app.core import scoring
from app.core.scoring import bpm_fit, rank, score, tag_overlap
from app.core.search_sql import Candidate
from app.models.api import SearchPlan


def cand(
    wid: str = "t1:mix:0",
    *,
    track_id: str | None = None,
    stem: str = "mix",
    start: float = 0.0,
    end: float = 10.0,
    tags: tuple[str, ...] = (),
    loop: float = 0.0,
    density: float = 0.5,
    distance: float = 0.5,
    bpm: float | None = 90.0,
) -> Candidate:
    tid = track_id or wid.split(":")[0]
    track: dict[str, Any] = {"id": tid, "bpm": bpm, "duration_s": 60.0, "beat_times": []}
    return Candidate(wid, tid, stem, start, end, tags, loop, density, distance, None, track)


def plan(**kw: Any) -> SearchPlan:
    return SearchPlan(clap_text="x", **kw)


def test_score_formula() -> None:
    c = cand(tags=("soul", "rhodes"), loop=0.8, distance=0.3, bpm=90)
    p = plan(must_tags=["soul", "rhodes", "melancholy"], bpm_range=(85, 95))
    expected = 0.6 * 0.7 + 0.2 * (2 / 3) + 0.1 * 1.0 + 0.1 * 0.8
    assert score(c, p) == pytest.approx(expected)


def test_prefer_sparse_subtracts_density() -> None:
    c = cand(distance=0.3, loop=0.5, density=0.4)
    assert score(c, plan(prefer_sparse=True)) == pytest.approx(score(c, plan()) - 0.15 * 0.4)


def test_score_is_clamped() -> None:
    assert score(cand(distance=0.0, loop=1.0, tags=("a",)), plan(must_tags=["a"])) == pytest.approx(1.0)
    worst = cand(distance=1.9, loop=0.0, density=1.0, bpm=200)
    assert score(worst, plan(must_tags=["a"], bpm_range=(60, 70), prefer_sparse=True)) == 0.0
    # negative cosine distance can't push sim above 1
    assert scoring.similarity(-0.01) == 1.0 and scoring.similarity(1.5) == 0.0


@pytest.mark.parametrize(
    ("bpm", "rng", "fit"),
    [
        (90, None, 1.0),
        (None, None, 1.0),
        (None, (85, 95), 0.5),
        (90, (85, 95), 1.0),
        (45, (85, 95), 1.0),  # half time of the range
        (180, (85, 95), 1.0),  # double time
        (100, (85, 95), 0.5),  # 5 bpm outside
        (110, (85, 95), 0.0),  # 15 bpm outside, half/double further away
        (90, (95, 85), 1.0),  # reversed range
    ],
)
def test_bpm_fit(bpm: float | None, rng: tuple[float, float] | None, fit: float) -> None:
    assert bpm_fit(bpm, rng) == pytest.approx(fit)


def test_tag_overlap() -> None:
    assert tag_overlap([], ["soul"]) == 0.5
    assert tag_overlap(["soul", "rhodes"], ["soul", "drum loop"]) == 0.5
    assert tag_overlap(["soul", "soul"], ["soul"]) == 1.0


def test_rank_sorts_by_score() -> None:
    out = rank([cand("a:mix:0", distance=0.6), cand("b:mix:0", distance=0.2), cand("c:mix:0", distance=0.4)], plan())
    assert [s.candidate.window_id for s in out] == ["b:mix:0", "c:mix:0", "a:mix:0"]
    assert all(0.0 <= s.score <= 1.0 for s in out)


def test_rank_caps_three_per_track() -> None:
    windows = [cand(f"t:mix:{i * 20000}", start=i * 20, end=i * 20 + 10, distance=0.1 + i / 100) for i in range(5)]
    out = rank([*windows, cand("u:mix:0", distance=0.5)], plan())
    assert [s.candidate.window_id for s in out] == ["t:mix:0", "t:mix:20000", "t:mix:40000", "u:mix:0"]


def test_rank_dedupes_overlapping_windows_of_same_stem() -> None:
    best = cand("t:mix:0", start=0, end=10, distance=0.1)
    half = cand("t:mix:5000", start=5, end=15, distance=0.2)  # 50% overlap → dropped
    less = cand("t:mix:6000", start=6, end=16, distance=0.3)  # 40% overlap → kept
    stem = cand("t:drums:0", stem="drums", start=0, end=10, distance=0.15)  # other stem → kept
    other = cand("u:mix:0", start=0, end=10, distance=0.25)  # other track → kept
    out = [s.candidate.window_id for s in rank([best, half, less, stem, other], plan())]
    assert out == ["t:mix:0", "t:drums:0", "u:mix:0", "t:mix:6000"]
    capped = [s.candidate.window_id for s in rank([best, half, less], plan())]
    assert capped == ["t:mix:0", "t:mix:6000"]
