"""Postgres access: psycopg 3 + pgvector, configured by DATABASE_URL (CONTRACT §4)."""

import psycopg


def connect() -> psycopg.Connection:
    """Open a connection to DATABASE_URL (session pooler) with the pgvector adapter registered."""
    raise NotImplementedError("WS1: common.db.connect")
