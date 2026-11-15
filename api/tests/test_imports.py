"""T7.2: POST /imports (size and format checks, storage path, placeholder row + analyze job).

The DB test runs only with BEATOPIA_DB_TESTS=1 and a DATABASE_URL, inside one transaction that is rolled back.
"""

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.core import imports
from app.core.settings import Settings
from app.models.api import ImportResponse
from app.routes import imports as imports_route

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 64
MP3_ID3 = b"ID3\x04\x00" + b"\x00" * 64
MP3_SYNC = b"\xff\xfb\x90\x64" + b"\x00" * 64
FLAC = b"fLaC" + b"\x00" * 64
OGG = b"OggS" + b"\x00" * 64
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 64


class FakePool:
    @contextmanager
    def connection(self) -> Iterator[object]:
        yield object()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def upload(local_path: str, path: str, content_type: str) -> str:
        with open(local_path, "rb") as f:
            seen["upload"] = (path, content_type, f.read())
        return f"https://x/{path}"

    def create(conn: object, track_id: str, title: str, original_path: str) -> str:
        seen["create"] = (track_id, title, original_path)
        return "6f1c1a4e-0000-4000-8000-000000000001"

    monkeypatch.setattr(imports_route.storage, "upload", upload)
    monkeypatch.setattr(imports, "create_import", create)
    return seen


@pytest.fixture
def client() -> TestClient:
    app = main.create_app(Settings.from_env({"SUPABASE_URL": "https://ref.supabase.co"}))
    app.state.pool = FakePool()
    return TestClient(app)


def _post(client: TestClient, name: str, data: bytes, session_id: str = "s-1") -> Any:
    return client.post(
        "/imports", files={"file": (name, data, "application/octet-stream")}, data={"session_id": session_id}
    )


@pytest.mark.parametrize(
    ("name", "data", "ctype"),
    [
        ("loop.wav", WAV, "audio/wav"),
        ("a.MP3", MP3_ID3, "audio/mpeg"),
        ("b.mp3", MP3_SYNC, "audio/mpeg"),
        ("c.flac", FLAC, "audio/flac"),
        ("d.ogg", OGG, "audio/ogg"),
        ("e.m4a", M4A, "audio/mp4"),
    ],
)
def test_import_ok(client: TestClient, calls: dict[str, Any], name: str, data: bytes, ctype: str) -> None:
    r = _post(client, name, data)
    assert r.status_code == 200, r.text
    body = ImportResponse.model_validate(r.json())
    assert re.fullmatch(r"imp_[0-9a-f]{8}", body.track_id)
    ext = name.rsplit(".", 1)[1].lower()
    assert calls["upload"] == (f"imports/{body.track_id}/original.{ext}", ctype, data)
    assert calls["create"] == (body.track_id, name.rsplit(".", 1)[0], f"imports/{body.track_id}/original.{ext}")
    assert body.job_id == "6f1c1a4e-0000-4000-8000-000000000001"


@pytest.mark.parametrize(
    ("name", "data", "why"),
    [
        ("notes.txt", WAV, "unsupported file type .txt"),
        ("noext", WAV, "(none)"),
        ("fake.wav", b"hello world, not audio" * 4, "does not look like audio"),
        ("x.wav", FLAC, "looks like flac"),
    ],
)
def test_import_unsupported(client: TestClient, calls: dict[str, Any], name: str, data: bytes, why: str) -> None:
    r = _post(client, name, data)
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_format" and why in r.json()["error"]["message"]
    assert "upload" not in calls


def test_import_too_large(client: TestClient, calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imports, "MAX_UPLOAD_BYTES", 1000)
    big = WAV + b"\x00" * 2000
    r = _post(client, "big.wav", big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "upload_too_large"
    assert "upload" not in calls


def test_import_empty_and_missing_fields(client: TestClient, calls: dict[str, Any]) -> None:
    assert _post(client, "empty.wav", b"").json()["error"]["code"] == "bad_request"
    assert _post(client, "a.wav", WAV, session_id=" ").json()["error"]["code"] == "bad_request"
    r = client.post("/imports", data={"session_id": "s"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


def test_title_from_filename() -> None:
    assert imports.title_from("My_Loop  01.wav") == "My Loop 01"
    assert imports.title_from("some/dir/beat.mp3") == "beat"
    assert imports.title_from("tab\there\x00.wav") == "tab here"
    assert imports.title_from("") == "Untitled import"
    assert len(imports.title_from("x" * 500 + ".wav")) == imports.MAX_TITLE


@pytest.mark.skipif(
    os.environ.get("BEATOPIA_DB_TESTS") != "1" or not os.environ.get("DATABASE_URL"),
    reason="set BEATOPIA_DB_TESTS=1 and DATABASE_URL to run against a real database",
)
def test_create_import_against_db() -> None:
    conn = psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None, connect_timeout=10)
    try:
        conn.execute("begin")  # outer transaction: create_import's own block becomes a savepoint
        tid = "imp_test0071"
        job_id = imports.create_import(conn, tid, "My loop", f"imports/{tid}/original.wav")
        track = conn.execute(
            "select source, title, license, attribution, duration_s, audio_path from tracks where id = %s", (tid,)
        ).fetchone()
        assert track == ("import", "My loop", "user-upload", "Uploaded by you", 0.0, f"imports/{tid}/mix.mp3")
        job = conn.execute("select kind, status, input from jobs where id = %s", (job_id,)).fetchone()
        assert job == ("analyze", "queued", {"track_id": tid, "path": f"imports/{tid}/original.wav"})
    finally:
        conn.rollback()
        conn.close()
