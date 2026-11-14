from unittest.mock import Mock

import pytest

from common import db


def test_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        db.connect()


def test_registers_adapter_and_returns_idle_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Mock()
    register = Mock()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test.invalid/db")
    monkeypatch.setattr(db.psycopg, "connect", Mock(return_value=connection))
    monkeypatch.setattr(db, "register_vector", register)
    assert db.connect() is connection
    register.assert_called_once_with(connection)
    connection.commit.assert_called_once()
    connection.close.assert_not_called()


def test_closes_connection_when_vector_extension_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Mock()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test.invalid/db")
    monkeypatch.setattr(db.psycopg, "connect", Mock(return_value=connection))
    monkeypatch.setattr(db, "register_vector", Mock(side_effect=RuntimeError("vector type not found")))
    with pytest.raises(RuntimeError, match="vector type not found"):
        db.connect()
    connection.close.assert_called_once()
    connection.commit.assert_not_called()
