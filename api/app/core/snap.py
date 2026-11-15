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


def snap_window(
    start_s: float, end_s: float, *, bpm: float | None, beat_times: Sequence[float], duration_s: float
) -> Snapped:
    end_s = min(end_s, duration_s)
    if not bpm or bpm <= 0 or not beat_times:
        return Snapped(round(start_s, 3), round(end_s, 3), NOMINAL_BARS)

    beats = sorted(beat_times)
    bar = bar_seconds(bpm)
    choices = ONE_SHOT_BARS if duration_s < ONE_SHOT_MAX_S else LOOP_BARS
    wanted = min(choices, key=lambda n: (abs(n * bar - (end_s - start_s)), n))
    i = nearest_beat(beats, start_s)

    for n in (b for b in SHRINK_ORDER if b <= wanted):
        length = n * bar
        # If the end runs past the track, move the start back by whole beats.
        j = i
        while j >= 0 and beats[j] + length > duration_s + END_TOLERANCE_S:
            j -= 1
        if j >= 0:
            start = beats[j]
            return Snapped(round(start, 3), round(min(start + length, duration_s), 3), n)
    # Not even one bar fits after the first beat (very short sound at a slow tempo): keep the raw bounds.
    return Snapped(round(start_s, 3), round(end_s, 3), 1)
