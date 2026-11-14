"""T3.2: bar snapping (CONTRACT §7.5)."""

import pytest

from app.core.snap import nearest_beat, snap_window


def grid(bpm: float, duration: float, offset: float = 0.0) -> list[float]:
    step = 60.0 / bpm
    return [offset + i * step for i in range(int((duration - offset) / step) + 1)]


def test_90_bpm_four_bars() -> None:
    s = snap_window(0.0, 10.0, bpm=90, beat_times=grid(90, 60), duration_s=60)
    assert s.bars == 4 and s.start_s == 0.0
    assert s.end_s - s.start_s == pytest.approx(10.667, abs=1e-3)


def test_start_snaps_to_nearest_beat() -> None:
    beats = grid(90, 60, offset=0.05)  # beats at 0.05, 0.717, 1.383, ...
    s = snap_window(5.2, 15.2, bpm=90, beat_times=beats, duration_s=60)
    assert nearest_beat(beats, 5.2) == 8
    assert s.start_s == pytest.approx(5.383, abs=1e-3)
    assert s.end_s - s.start_s == pytest.approx(10.667, abs=1e-3)


def test_length_picks_closest_bar_count() -> None:
    # 180 bpm: 4 bars = 5.33 s, 8 bars = 10.67 s → a 10 s window becomes 8 bars
    assert snap_window(0, 10, bpm=180, beat_times=grid(180, 60), duration_s=60).bars == 8
    # 60 bpm: 4 bars = 16 s is still the closest loop length
    s = snap_window(0, 10, bpm=60, beat_times=grid(60, 60), duration_s=60)
    assert s.bars == 4 and s.end_s == pytest.approx(16.0)


def test_one_shot_uses_one_or_two_bars() -> None:
    # 3 s sound at 120 bpm: bar = 2 s → 1 bar (2 s) is closest to the 3 s window... 2 bars (4 s) doesn't fit
    s = snap_window(0, 3.0, bpm=120, beat_times=grid(120, 3.0), duration_s=3.0)
    assert s.bars == 1 and s.end_s == pytest.approx(2.0)
    # 3.9 s sound at 128 bpm: bar = 1.875 s → 2 bars (3.75 s) fits and is closest
    s = snap_window(0, 3.9, bpm=128, beat_times=grid(128, 3.9), duration_s=3.9)
    assert s.bars == 2 and s.end_s == pytest.approx(3.75)


def test_end_clamp_moves_start_back_by_whole_beats() -> None:
    beats = grid(90, 30)
    s = snap_window(25.0, 30.0, bpm=90, beat_times=beats, duration_s=30)
    assert s.bars == 4
    assert s.end_s <= 30.0 and s.end_s - s.start_s == pytest.approx(10.667, abs=1e-3)
    assert any(abs(b - s.start_s) < 1e-3 for b in beats)  # still on a beat
    assert s.start_s < 25.0


def test_bars_drop_when_track_is_too_short() -> None:
    # 6 s track at 90 bpm: 4 bars (10.67 s) can't fit → 2 bars (5.33 s)
    s = snap_window(0, 6.0, bpm=90, beat_times=grid(90, 6.0), duration_s=6.0)
    assert s.bars == 2 and s.end_s == pytest.approx(5.333, abs=1e-3)
    # 1.5 s sound at 60 bpm (bar = 4 s): nothing fits → raw bounds, 1 bar
    s = snap_window(0, 1.5, bpm=60, beat_times=[0.0, 1.0], duration_s=1.5)
    assert (s.start_s, s.end_s, s.bars) == (0.0, 1.5, 1)


def test_no_bpm_or_no_beats_keeps_raw_bounds() -> None:
    assert snap_window(5.0, 15.0, bpm=None, beat_times=grid(90, 60), duration_s=60) == snap_window(
        5.0, 15.0, bpm=90, beat_times=[], duration_s=60
    )
    s = snap_window(5.0, 15.0, bpm=None, beat_times=[], duration_s=12.0)
    assert (s.start_s, s.end_s, s.bars) == (5.0, 12.0, 4)
