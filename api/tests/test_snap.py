"""T3.2: bar snapping (CONTRACT §7.5)."""

import pytest

from app.core.snap import nearest_beat, piece_bounds, snap_window


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


# ---- processed-excerpt joins (issue #13) ----


def joined_beats(bpm: float, first_offset: float, second_offset: float) -> list[float]:
    """A 180 s library track: first 120 s + a 60 s middle excerpt, each beat-tracked separately (WS1 ingest)."""
    first = [b for b in grid(bpm, 120, first_offset) if b < 120]
    second = [b for b in grid(bpm, 180, second_offset) if b >= second_offset]
    return first + second


@pytest.mark.parametrize(
    ("start", "end", "bpm", "beats"),
    [
        # q06 jam_1030279:mix:110000 used to snap to [110.097, 120.685]
        (110.0, 120.0, 90.6661, joined_beats(90.6661, 0.097, 120.31)),
        # q05 jam_1432369:bass:120000 used to snap to [119.304, 130.264]
        (120.0, 130.0, 87.5927, joined_beats(87.5927, 0.0, 120.2)),
        # q16 jam_1348228:mix:120000 used to snap to [119.954, 128.955]
        (120.0, 130.0, 106.658, joined_beats(106.658, 119.954 - 213 * 60 / 106.658, 120.3)),
    ],
)
def test_snapped_windows_stay_inside_their_excerpt(start: float, end: float, bpm: float, beats: list[float]) -> None:
    old = snap_window(start, end, bpm=bpm, beat_times=beats, duration_s=180.0)
    assert old.start_s < 120 < old.end_s  # the bug: without piece bounds the window crosses the join
    piece = piece_bounds(start, end, duration_s=180.0, source="jamendo")
    s = snap_window(start, end, bpm=bpm, beat_times=beats, duration_s=180.0, piece=piece)
    assert piece[0] <= s.start_s < s.end_s <= piece[1]
    assert not (s.start_s < 120 < s.end_s)
    assert s.start_s in [round(b, 3) for b in beats] and s.bars in (4, 8, 16)


def test_no_beat_near_the_window_keeps_its_bounds() -> None:
    """jam_1432369: the tracker found no beat in 119.3..129.72 (just after the join); [120, 130] must not jump."""
    beats = [*grid(87.5927, 119.31, 0.0), *grid(87.5927, 180, 129.72)]
    piece = piece_bounds(120, 130, duration_s=180.0, source="jamendo")
    s = snap_window(120.0, 130.0, bpm=87.5927, beat_times=beats, duration_s=180.0, piece=piece)
    assert (s.start_s, s.end_s, s.bars) == (120.0, 130.0, 4)


def test_piece_bounds() -> None:
    assert piece_bounds(110, 120, duration_s=180.0, source="jamendo") == (0.0, 120.0)
    assert piece_bounds(120, 130, duration_s=180.0, source="jamendo") == (120.0, 180.0)
    assert piece_bounds(170, 180, duration_s=180.02, source="jamendo") == (120.0, 180.02)
    assert piece_bounds(115, 125, duration_s=177.3, source="jamendo") == (0.0, 177.3)  # stored whole: no join
    assert piece_bounds(115, 125, duration_s=180.0, source="import") == (0.0, 180.0)  # full uploaded timeline
    assert piece_bounds(0, 10, duration_s=12.6, source="freesound") == (0.0, 12.6)


def test_unjoined_tracks_snap_as_before() -> None:
    beats = grid(90, 177.3, 0.05)
    for start in (0.0, 55.0, 115.0, 167.3):
        plain = snap_window(start, start + 10, bpm=90, beat_times=beats, duration_s=177.3)
        piece = piece_bounds(start, start + 10, duration_s=177.3, source="jamendo")
        assert snap_window(start, start + 10, bpm=90, beat_times=beats, duration_s=177.3, piece=piece) == plain
