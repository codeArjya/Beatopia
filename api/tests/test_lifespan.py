"""T1.2: lifespan (pool + CLAP warm-up), db dependency, timing log line + Server-Timing header."""

import asyncio
import json
import logging
import time

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app import main
from app.core import db, embed
from app.core.settings import Settings
from app.core.timing import note, stage

REAL = Settings.from_env(
    {"DATABASE_URL": "postgresql://u:p@localhost:5432/x", "SUPABASE_URL": "https://ref.supabase.co"}
)


class FakePool:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_real_mode_opens_and_closes_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FakePool()
    monkeypatch.setattr(db, "open_pool", lambda s: pool)
    monkeypatch.setattr(embed, "warm", lambda: True)

    real = APIRouter()

    @real.get("/pool-check")
    def pool_check(p: object = Depends(db.get_pool)) -> dict[str, bool]:
        return {"same": p is pool}

    monkeypatch.setattr(main, "REAL_ROUTERS", [real])
    app = main.create_app(REAL)
    with TestClient(app) as client:
        assert client.get("/pool-check").json() == {"same": True}
        assert app.state.clap_ready is True
    assert pool.closed and app.state.pool is None


def test_real_mode_fails_loudly_when_db_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_: Settings) -> None:
        raise RuntimeError("could not connect to DATABASE_URL")

    monkeypatch.setattr(db, "open_pool", boom)
    with pytest.raises(RuntimeError, match="could not connect"), TestClient(main.create_app(REAL)):
        pass


def test_open_pool_requires_database_url() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        db.open_pool(Settings.from_env({}))


def test_open_pool_reports_unreachable_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "CONNECT_TIMEOUT_S", 2)  # libpq minimum
    unreachable = Settings.from_env({"DATABASE_URL": "postgresql://u:p@127.0.0.1:1/x"})
    with pytest.raises(RuntimeError, match="SESSION pooler"):
        db.open_pool(unreachable)


def test_fixture_mode_skips_db_and_clap(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: object) -> None:
        raise AssertionError("must not be called in fixture mode")

    monkeypatch.setattr(db, "open_pool", fail)
    monkeypatch.setattr(embed, "warm", fail)
    with TestClient(main.create_app(Settings.from_env({"USE_FIXTURES": "1"}))) as client:
        assert client.get("/health").json() == {"ok": True}


def test_clap_warm_tolerates_ws1_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    def stub(_: list[str]) -> None:
        raise NotImplementedError("WS1")

    monkeypatch.setattr(embed.clap, "embed_text", stub)
    assert embed.warm() is False


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def test_timing_log_line_and_server_timing_header(monkeypatch: pytest.MonkeyPatch) -> None:
    real = APIRouter()

    @real.get("/timed")
    async def timed() -> dict[str, bool]:
        with stage("plan"):
            time.sleep(0.02)

        def work() -> None:
            with stage("sql"):  # stages recorded inside asyncio.to_thread too
                pass

        await asyncio.to_thread(work)
        note(n=3, plan_cached=False)
        return {"ok": True}

    monkeypatch.setattr(main, "REAL_ROUTERS", [real])
    capture = _Capture()
    logging.getLogger("app.request").addHandler(capture)
    try:
        client = TestClient(main.create_app(REAL))  # no `with`: lifespan (and the DB) not needed here
        r = client.get("/timed")
        client.get("/missing")
    finally:
        logging.getLogger("app.request").removeHandler(capture)

    header = r.headers["server-timing"]
    assert header.startswith("plan;dur=") and "sql;dur=" in header and "total;dur=" in header
    line = json.loads(capture.lines[0])
    assert line["path"] == "/timed" and line["status"] == 200
    assert line["plan_ms"] >= 10 and "sql_ms" in line
    assert line["n"] == 3 and line["plan_cached"] is False
    assert json.loads(capture.lines[1])["status"] == 404
