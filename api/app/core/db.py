"""Postgres connection pool (psycopg 3 + pgvector) on the Supabase SESSION pooler."""

from __future__ import annotations

import logging

import psycopg
from fastapi import Request
from pgvector.psycopg import register_vector
from psycopg import pq
from psycopg_pool import ConnectionPool, PoolTimeout

from app.core.settings import Settings

log = logging.getLogger("app.db")

CONNECT_TIMEOUT_S = 10


def _configure(conn: psycopg.Connection) -> None:
    register_vector(conn)
    if conn.info.transaction_status != pq.TransactionStatus.IDLE:
        conn.commit()  # the pool rejects connections that configure() leaves inside a transaction


def _probe(url: str) -> None:
    """One direct connection first, so a bad URL or missing extension fails with the real error message."""
    try:
        with psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_S, prepare_threshold=None) as conn:
            _configure(conn)
            conn.execute("select 1")
    except psycopg.ProgrammingError as exc:
        raise RuntimeError(f"database is missing pgvector ({exc}); run `make db-init`") from exc
    except psycopg.OperationalError as exc:
        raise RuntimeError(f"could not connect to DATABASE_URL (use the SESSION pooler, port 5432): {exc}") from exc


def open_pool(settings: Settings) -> ConnectionPool:
    missing = settings.missing("database_url")
    if missing:
        raise RuntimeError(f"real mode needs {', '.join(missing)} (or set USE_FIXTURES=1)")
    assert settings.database_url is not None
    _probe(settings.database_url)
    pool = ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=5,
        kwargs={"prepare_threshold": None, "connect_timeout": CONNECT_TIMEOUT_S},
        configure=_configure,
        open=False,
        name="api",
    )
    try:
        pool.open(wait=True, timeout=CONNECT_TIMEOUT_S)
    except PoolTimeout as exc:
        pool.close()
        raise RuntimeError(f"database pool did not open within {CONNECT_TIMEOUT_S} s") from exc
    log.info("db pool open (min 1, max 5)")
    return pool


def get_pool(request: Request) -> ConnectionPool:
    """FastAPI dependency: the pool opened in the lifespan."""
    pool: ConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise RuntimeError("db pool is not open (fixture mode, or lifespan did not run)")
    return pool
