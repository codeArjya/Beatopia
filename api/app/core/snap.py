"""Bar snapping (CONTRACT §7.5): start on the nearest beat, length = 1/2/4/8/16 bars at the track bpm."""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Bars = Literal[1, 2, 4, 8, 16]

BEATS_PER_BAR = 4
LOOP_BARS: tuple[Bars, ...] = (4, 8, 16)
ONE_SHOT_BARS: tuple[Bars, ...] = (1, 2)
ONE_SHOT_MAX_S = 4.0  # tracks shorter than this are one-shots
NOMINAL_BARS: Bars = 4  # reported when there is no bpm or no beat grid (raw window bounds kept)
SHRINK_ORDER: tuple[Bars, ...] = (16, 8, 4, 2, 1)
END_TOLERANCE_S = 0.01  # an end this close past the track end still fits (and is clamped to it)
EXCERPT_JOIN_S = 120.0  # WS1 ingest: first 120 s + a 60 s middle excerpt for songs over 180 s
JOINED_DURATION_S = 180.0
JOIN_MATCH_S = 0.05


@dataclass(frozen=True)
class Snapped:
    start_s: float
    end_s: float
    bars: Bars


def bar_seconds(bpm: float) -> float:
    return BEATS_PER_BAR * 60.0 / bpm


def nearest_beat(beat_times: Sequence[float], t: float) -> int:
    i = bisect.bisect_left(beat_times, t)
    if i == 0:
        return 0
    if i == len(beat_times):
        return len(beat_times) - 1
    return i if beat_times[i] - t < t - beat_times[i - 1] else i - 1


def piece_bounds(start_s: float, end_s: float, *, duration_s: float, source: str | None) -> tuple[float, float]:
    """The processed excerpt a window lies in, on the stored-mix timeline (WS1 ingest `excerpt_ranges`).

    Library songs longer than 180 s are stored as their first 120 s plus a 60 s middle excerpt, joined at 120 s, so
    their stored mix (and full-length stems) is exactly 180 s; shorter songs are stored whole. Ingest never makes a
    window across the join, and a snapped window must not cross it either (the audio jumps there). Imports keep
    their full uploaded timeline. Checked on the dev DB: all 117 library tracks of 180.0 s have no window crossing
    120 s, every 120–179.5 s track does.
    """
    if source != "import" and abs(duration_s - JOINED_DURATION_S) <= JOIN_MATCH_S:
        return (EXCERPT_JOIN_S, duration_s) if start_s >= EXCERPT_JOIN_S - JOIN_MATCH_S else (0.0, EXCERPT_JOIN_S)
    return 0.0, duration_s


def snap_window(
    start_s: float,
    end_s: float,
    *,
    bpm: float | None,
    beat_times: Sequence[float],
    duration_s: float,
    piece: tuple[float, float] | None = None,
) -> Snapped:
    """`piece`: the processed excerpt the window lies in (`piece_bounds`); the snapped window stays inside it."""
    lo, hi = piece if piece is not None else (0.0, duration_s)
    hi = min(hi, duration_s)
    start_s, end_s = max(start_s, lo), min(end_s, hi)
    if not bpm or bpm <= 0 or not beat_times:
        return Snapped(round(start_s, 3), round(end_s, 3), NOMINAL_BARS)

    beats = sorted(b for b in beat_times if lo <= b < hi)  # a beat before the join must not start a later window
    if not beats:
        return Snapped(round(start_s, 3), round(end_s, 3), NOMINAL_BARS)
    bar = bar_seconds(bpm)
    choices = ONE_SHOT_BARS if duration_s < ONE_SHOT_MAX_S else LOOP_BARS
    wanted = min(choices, key=lambda n: (abs(n * bar - (end_s - start_s)), n))
    i = nearest_beat(beats, start_s)
    if abs(beats[i] - start_s) > bar:
        # No beat near the window (the tracker found none there, e.g. the first seconds after a join): snapping
        # would move the sample away from the window that was searched and scored. Keep the stored bounds.
        return Snapped(round(start_s, 3), round(end_s, 3), NOMINAL_BARS)

    for n in (b for b in SHRINK_ORDER if b <= wanted):
        length = n * bar
        # If the end runs past the piece (the track end or the excerpt join), move the start back by whole beats.
        j = i
        while j >= 0 and beats[j] + length > hi + END_TOLERANCE_S:
            j -= 1
        if j >= 0:
            start = beats[j]
            return Snapped(round(start, 3), round(min(start + length, hi), 3), n)
    # Not even one bar fits after the first beat (very short sound at a slow tempo): keep the raw bounds.
    return Snapped(round(start_s, 3), round(end_s, 3), 1)
