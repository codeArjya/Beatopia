"""T6.3: bench.py helpers (Server-Timing parsing, percentiles)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bench import parse_server_timing, percentile  # noqa: E402

from app.core.timing import Timer, server_timing  # noqa: E402


def test_parse_server_timing_roundtrips_our_header() -> None:
    timer = Timer()
    timer.stages.update({"plan": 1234.5, "embed": 98.0, "sql": 12.25})
    parsed = parse_server_timing(server_timing(timer, 1400.0))
    assert parsed == {"plan": 1234.5, "embed": 98.0, "sql": 12.2, "total": 1400.0}


def test_parse_server_timing_tolerates_junk() -> None:
    assert parse_server_timing("") == {}
    assert parse_server_timing('cache;desc="hit", db;dur=bad, app;dur=5, app;dur=2') == {"app": 7.0}


def test_percentile_nearest_rank() -> None:
    values = [float(v) for v in range(1, 21)]
    assert percentile(values, 50) == 10.0
    assert percentile(values, 95) == 19.0
    assert percentile([5.0], 95) == 5.0
