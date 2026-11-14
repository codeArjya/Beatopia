"""T1.1: settings, error shapes, fixture mode vs real mode."""

from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app import main
from app.core.errors import ApiException, upstream_error
from app.core.settings import DEFAULT_GEMINI_MODEL, Settings, get_settings
from app.main import create_app


def test_settings_defaults() -> None:
    s = Settings.from_env({})
    assert s.gemini_model == DEFAULT_GEMINI_MODEL == "gemini-3.8-flash"
    assert s.web_origins == ("http://localhost:3000",)
    assert not s.use_fixtures and not s.gemini_degraded
    assert s.database_url is None
    assert s.fixtures_dir == Path(__file__).resolve().parents[2] / "shared" / "fixtures"
    assert s.vocab_path.name == "vocab.txt"


def test_settings_parsing() -> None:
    s = Settings.from_env(
        {
            "GEMINI_MODEL": "gemini-3.6-flash",
            "GEMINI_DEGRADED": "1",
            "USE_FIXTURES": "true",
            "WEB_ORIGIN": " http://localhost:3000 , https://beatopia.vercel.app,",
            "DATABASE_URL": "  ",
            "FREESOUND_API_KEY": "k",
        }
    )
    assert s.gemini_model == "gemini-3.6-flash"
    assert s.gemini_degraded and s.use_fixtures
    assert s.web_origins == ("http://localhost:3000", "https://beatopia.vercel.app")
    assert s.database_url is None  # blank counts as unset
    assert s.missing("database_url", "freesound_api_key") == ["DATABASE_URL"]
    with pytest.raises(ValueError):
        s.missing("nope")


def test_conftest_selects_fixture_mode() -> None:
    assert get_settings().use_fixtures
    assert main.app.state.settings.use_fixtures


def test_unknown_route_and_method_shapes() -> None:
    client = TestClient(main.app)
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    r = client.get("/search")  # POST-only
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "bad_request"


def test_validation_message_names_the_field() -> None:
    r = TestClient(main.app).post("/search", json={"text": "x", "limit": 99, "session_id": "s"})
    assert r.status_code == 400
    assert "limit" in r.json()["error"]["message"]


def test_api_exception_status_mapping() -> None:
    assert upstream_error("gemini down").status == 502
    assert ApiException("upload_too_large", "big").status == 413
    assert ApiException("bad_request", "x", status=422).status == 422


def _real_settings() -> Settings:
    return Settings.from_env({"WEB_ORIGIN": "https://app.example"})


def test_real_router_shadows_fixture_route(monkeypatch: pytest.MonkeyPatch) -> None:
    real = APIRouter()

    @real.get("/chips")
    def real_chips() -> dict[str, list[object]]:
        return {"categories": []}

    @real.get("/boom")
    def boom() -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr(main, "REAL_ROUTERS", [real])

    client = TestClient(create_app(_real_settings()), raise_server_exceptions=False)
    assert client.get("/chips").json() == {"categories": []}
    # not implemented yet → still the fixture stand-in
    assert len(client.post("/search", json={"session_id": "s"}).json()["results"]) == 8
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "something went wrong on the server"}}

    # fixture mode ignores real routers entirely
    fixture_client = TestClient(create_app(Settings.from_env({"USE_FIXTURES": "1"})))
    assert len(fixture_client.get("/chips").json()["categories"]) == 5
    assert fixture_client.get("/boom").status_code == 404


def test_cors_uses_configured_origins() -> None:
    client = TestClient(create_app(_real_settings()))
    preflight = {"Origin": "https://app.example", "Access-Control-Request-Method": "POST"}
    assert client.options("/search", headers=preflight).headers["access-control-allow-origin"] == "https://app.example"
    evil = {"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    assert "access-control-allow-origin" not in client.options("/search", headers=evil).headers
