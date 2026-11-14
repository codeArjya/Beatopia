"""Postgres access: psycopg 3 + pgvector, configured by DATABASE_URL (CONTRACT §4)."""

import os

import psycopg
from pgvector.psycopg import register_vector


def connect() -> psycopg.Connection:
    """Open a connection to DATABASE_URL (session pooler) with the pgvector adapter registered."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    connection = psycopg.connect(url, connect_timeout=10)
    try:
        register_vector(connection)
        # Adapter discovery must not leave callers idle in a transaction.
        connection.commit()
    except Exception:
        connection.close()
        raise
    return connection
