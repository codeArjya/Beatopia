"""T3.1: the search SQL filters (CONTRACT §7.3).

Unit tests check the generated WHERE clause. The DB test runs only with BEATOPIA_DB_TESTS=1 and a DATABASE_URL: it
creates temp tables that shadow `tracks`/`windows`/`notes` (pg_temp is searched first), seeds them inside one
transaction and always rolls back, so the shared database (and its real seed rows) is never touched.
"""

import os
from collections.abc import Iterator
from typing import Any

import numpy as np
import psycopg
import pytest
from pgvector.psycopg import register_vector

from app.core import search_sql
from app.core.search_sql import fetch_candidates, where_clause
from app.models.api import SearchPlan


def plan(**kw: Any) -> SearchPlan:
    return SearchPlan(clap_text="x", **kw)


def test_where_always_excludes_imports() -> None:
    where, params = where_clause(plan(), relax=False)
    assert where == "t.source <> 'import'" and params == {}


def test_where_all_filters() -> None:
    p = plan(must_tags=["soul"], exclude_tags=["kick"], bpm_range=(95, 85), key="A minor", stems_wanted=["drums"])
    where, params = where_clause(p, relax=False)
    assert "w.tags @> %(must)s" in where and "not (w.tags && %(exclude)s)" in where
    assert "t.bpm * 2 between" in where and "t.bpm / 2 between" in where and "t.bpm is null" in where
    assert "t.key = %(key)s" in where and "w.stem = any(%(stems)s)" in where
    assert params == {
        "must": ["soul"],
        "exclude": ["kick"],
        "bpm_lo": 85,
        "bpm_hi": 95,
        "key": "A minor",
        "stems": ["drums"],
    }
    relaxed, _ = where_clause(p, relax=True)
    assert "w.tags && %(must)s" in relaxed and "@>" not in relaxed


# ---- DB integration (opt-in) ----

E0 = np.eye(512, dtype=np.float32)[0]
E1 = np.eye(512, dtype=np.float32)[1]


def vec(cos: float) -> np.ndarray:
    """Unit vector at cosine `cos` to E0, so `<=> E0` = 1 - cos."""
    return (cos * E0 + np.sqrt(1 - cos**2) * E1).astype(np.float32)


TRACKS = [  # id, source, bpm, key
    ("t_a", "jamendo", 90.0, "A minor"),
    ("t_b", "freesound", 45.0, "C major"),
    ("t_c", "freesound", None, None),
    ("t_d", "jamendo", 120.0, "A minor"),
    ("t_imp", "import", 90.0, "A minor"),
]
WINDOWS = [  # id, stem, cos to query, tags
    ("t_a:mix:0", "mix", 0.95, ["soul", "rhodes"]),
    ("t_a:drums:0", "drums", 0.60, ["drum loop", "soul"]),
    ("t_b:mix:0", "mix", 0.90, ["soul", "rhodes", "vocal chop"]),
    ("t_c:mix:0", "mix", 0.80, ["soul"]),
    ("t_d:mix:0", "mix", 0.85, ["rhodes"]),
    ("t_imp:mix:0", "mix", 0.99, ["soul", "rhodes"]),
]


@pytest.fixture
def seeded() -> Iterator[psycopg.Connection]:
    if os.environ.get("BEATOPIA_DB_TESTS") != "1" or not os.environ.get("DATABASE_URL"):
        pytest.skip("set BEATOPIA_DB_TESTS=1 and DATABASE_URL to run against a real database")
    conn = psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None, connect_timeout=10)
    register_vector(conn)
    try:
        for table in ("tracks", "windows", "notes"):
            conn.execute(f"create temp table {table} (like public.{table} including all)")
        for tid, source, bpm, key in TRACKS:
            conn.execute(
                "insert into tracks (id, source, title, license, attribution, duration_s, bpm, key, audio_path)"
                " values (%s, %s, %s, 'CC0', 'test', 30, %s, %s, %s)",
                (tid, source, tid.upper(), bpm, key, f"tracks/{tid}/mix.mp3"),
            )
        for wid, stem, cos, tags in WINDOWS:
            conn.execute(
                "insert into windows (id, track_id, stem, start_s, end_s, embedding, tags, loopability, density)"
                " values (%s, %s, %s, 0, 10, %s, %s, 0.5, 0.5)",
                (wid, wid.split(":")[0], stem, vec(cos), tags),
            )
        conn.execute("insert into notes (window_id, text, model) values ('t_a:mix:0', 'cached note', 'test')")
        yield conn
    finally:
        conn.rollback()
        conn.close()


def ids(conn: psycopg.Connection, p: SearchPlan, **kw: Any) -> list[str]:
    rows, _ = fetch_candidates(conn, p, E0, **kw)
    return [r.window_id for r in rows]


def test_db_orders_by_distance_and_skips_imports(seeded: psycopg.Connection) -> None:
    rows, relaxed = fetch_candidates(seeded, plan(), E0)
    assert [r.window_id for r in rows] == ["t_a:mix:0", "t_b:mix:0", "t_d:mix:0", "t_c:mix:0", "t_a:drums:0"]
    assert not relaxed
    assert rows[0].distance == pytest.approx(0.05, abs=1e-4)
    assert rows[0].why == "cached note" and rows[1].why is None
    assert rows[0].track["audio_path"] == "tracks/t_a/mix.mp3" and rows[0].bpm == 90.0
    assert rows[0].tags == ("soul", "rhodes")
    assert ids(seeded, plan(), limit=2) == ["t_a:mix:0", "t_b:mix:0"]


def test_db_must_tags_relax_to_overlap(seeded: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    p = plan(must_tags=["soul", "rhodes"])
    monkeypatch.setattr(search_sql, "RELAX_BELOW", 2)
    rows, relaxed = fetch_candidates(seeded, p, E0)
    assert [r.window_id for r in rows] == ["t_a:mix:0", "t_b:mix:0"] and not relaxed
    monkeypatch.setattr(search_sql, "RELAX_BELOW", 3)
    rows, relaxed = fetch_candidates(seeded, p, E0)
    assert relaxed and len(rows) == 5


def test_db_exclude_key_stems(seeded: psycopg.Connection) -> None:
    assert "t_b:mix:0" not in ids(seeded, plan(exclude_tags=["vocal chop", "kick"]))
    assert ids(seeded, plan(key="A minor")) == ["t_a:mix:0", "t_d:mix:0", "t_a:drums:0"]
    assert ids(seeded, plan(stems_wanted=["drums", "bass"])) == ["t_a:drums:0"]


def test_db_bpm_half_double_and_null(seeded: psycopg.Connection) -> None:
    # 90 matches; 45 matches by double time; null bpm passes; 120 is out
    assert ids(seeded, plan(bpm_range=(85, 95))) == ["t_a:mix:0", "t_b:mix:0", "t_c:mix:0", "t_a:drums:0"]
    # 90 matches 180 by double time; 45 and 120 don't
    assert ids(seeded, plan(bpm_range=(175, 185))) == ["t_a:mix:0", "t_c:mix:0", "t_a:drums:0"]
