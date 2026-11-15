"""T5.1 contract test: every CONTRACT §6 endpoint, validated against shared/schema and the shared fixtures' shapes.

Targets
- default: the app in fixture mode, in process (TestClient), so `make test` always checks the fixtures path;
- `API_URL=http://localhost:8000` (or the production URL): a running server over HTTP, e.g. local real mode:

      make dev-api        # real mode, with the CLAP_* / GEMINI_MODEL env set
      API_URL=http://localhost:8000 uv run --project api pytest api/tests/test_contract.py -v

Each 2xx body is validated against `shared/schema/api.schema.json` (what the web client is typed against) and the
Pydantic model, and its key sets are compared recursively with the matching fixture, so fixtures and live
responses have identical shapes. Error bodies must be `{"error": ApiError}`.

Against a live server, calls that create state (a stems job, an import, an event row) only run with
`CONTRACT_WRITES=1`. `/search`, `/why` (fills the notes cache) and `/assist` always run.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from functools import cache
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from app.core.settings import REPO_ROOT, Settings
from app.main import create_app
from app.models import api as models
from app.models.ops import AssistResponse

API_URL = os.environ.get("API_URL", "").rstrip("/")
LIVE = bool(API_URL)
WRITES = not LIVE or os.environ.get("CONTRACT_WRITES") == "1"
SESSION = f"contract-test-{uuid.uuid4().hex[:8]}"

SCHEMA = json.loads((REPO_ROOT / "shared" / "schema" / "api.schema.json").read_text("utf-8"))
FIXTURES = REPO_ROOT / "shared" / "fixtures"
FIXTURE_WAV = REPO_ROOT / "web" / "public" / "fixtures" / "audio" / "mix.wav"

needs_writes = pytest.mark.skipif(not WRITES, reason="live server: set CONTRACT_WRITES=1 to create jobs/rows")
fixture_mode_only = pytest.mark.skipif(LIVE, reason="fixture handlers only")
live_only = pytest.mark.skipif(not LIVE, reason="fixture handlers answer any id; checked against a real server")


@cache
def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))


def validate(body: Any, name: str, model: type[BaseModel] | None = None) -> None:
    Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]}).validate(body)
    if model is not None:
        model.model_validate(body)


def _partner(item: dict[str, Any], options: list[Any]) -> dict[str, Any] | None:
    """The fixture element to compare `item` with: same discriminator (op / kind / category / stem) if any."""
    dicts = [o for o in options if isinstance(o, dict)]
    for key in ("op", "kind", "category"):
        if key in item:
            same = [o for o in dicts if o.get(key) == item[key]]
            return same[0] if same else None
    return dicts[0] if dicts else None


def same_shape(actual: Any, expected: Any, path: str = "$") -> list[str]:
    """Key-set differences between a response and its fixture, recursively (values and list lengths ignored)."""
    problems: list[str] = []
    if isinstance(actual, dict) and isinstance(expected, dict):
        # A key that is null on one side and absent on the other is the same to a client (optional field).
        extra = sorted(k for k in set(actual) - set(expected) if actual[k] is not None)
        missing = sorted(k for k in set(expected) - set(actual) if expected[k] is not None)
        if extra or missing:
            problems.append(f"{path}: extra keys {extra}, missing keys {missing}")
        for k in set(actual) & set(expected):
            problems += same_shape(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(actual, list) and isinstance(expected, list):
        for i, item in enumerate(actual):
            partner = _partner(item, expected) if isinstance(item, dict) else None
            if partner is not None:
                problems += same_shape(item, partner, f"{path}[{i}]")
    return problems


def assert_shape(actual: Any, fixture_name: str) -> None:
    problems = same_shape(actual, fixture(fixture_name))
    assert not problems, f"shape differs from {fixture_name}.json: " + "; ".join(problems)


def assert_error(r: httpx.Response, status: int, code: str) -> None:
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"}
    validate(body["error"], "ApiError", models.ApiError)
    assert body["error"]["code"] == code


# ---- target ----


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    if LIVE:
        with httpx.Client(base_url=API_URL, timeout=60) as client:
            yield client
    else:
        with TestClient(create_app(Settings.from_env({"USE_FIXTURES": "1"}))) as client:
            yield client


@pytest.fixture(scope="module")
def search_body(api: httpx.Client) -> dict[str, Any]:
    r = api.post("/search", json={"text": "dusty soul keys", "limit": 8, "session_id": SESSION})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["results"], "the contract test needs at least one search result"
    return body


@pytest.fixture(scope="module")
def track_body(api: httpx.Client, search_body: dict[str, Any]) -> dict[str, Any]:
    r = api.get(f"/tracks/{search_body['results'][0]['track']['id']}")
    assert r.status_code == 200, r.text
    return r.json()


# ---- 2xx shapes ----


def test_health(api: httpx.Client) -> None:
    r = api.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_chips(api: httpx.Client) -> None:
    r = api.get("/chips")
    assert r.status_code == 200, r.text
    validate(r.json(), "ChipsResponse", models.ChipsResponse)
    assert_shape(r.json(), "chips")
    assert [c["id"] for c in r.json()["categories"]] == ["instrument", "genre", "mood", "tempo", "key"]


def test_search_text(search_body: dict[str, Any]) -> None:
    validate(search_body, "SearchResponse", models.SearchResponse)
    assert_shape(search_body, "search")
    assert len(search_body["results"]) <= 8
    assert all(0 <= x["score"] <= 1 for x in search_body["results"])
    assert all(x["track"]["license"] and "attribution" in x["track"] for x in search_body["results"])


def test_search_chips_only(api: httpx.Client) -> None:
    r = api.post("/search", json={"chips": ["inst.rhodes", "tempo.90"], "limit": 3, "session_id": SESSION})
    assert r.status_code == 200, r.text
    validate(r.json(), "SearchResponse", models.SearchResponse)
    assert_shape(r.json(), "search")
    if LIVE:  # the fixture handler always returns the 8 fixture results
        assert len(r.json()["results"]) <= 3


def test_track_detail(track_body: dict[str, Any], search_body: dict[str, Any]) -> None:
    validate(track_body, "TrackDetail", models.TrackDetail)
    assert_shape(track_body, "track_detail")
    if LIVE:
        assert track_body["track"]["id"] == search_body["results"][0]["track"]["id"]


def test_why(api: httpx.Client, search_body: dict[str, Any]) -> None:
    wid = search_body["results"][0]["window_id"]
    r = api.post("/why", json={"window_id": wid})
    assert r.status_code == 200, r.text
    validate(r.json(), "WhyResponse", models.WhyResponse)
    assert_shape(r.json(), "why")
    assert r.json()["window_id"] == wid and r.json()["note"].strip()


def _editor_state(track: dict[str, Any]) -> dict[str, Any]:
    end = min(10.667, float(track["track"]["duration_s"]))
    return {
        "bpm": track["track"]["bpm"],
        "clips": [
            {
                "id": "c1",
                "source": {
                    "track_id": track["track"]["id"],
                    "stem": "mix",
                    "audio_url": track["audio_url"],
                    "start_s": 0.0,
                    "end_s": end,
                },
            }
        ],
        "ops": [],
        "arrangement": [],
    }


def test_assist(api: httpx.Client, track_body: dict[str, Any]) -> None:
    req = {
        "messages": [{"role": "user", "content": "chop this into 4 and reverse the last one"}],
        "editor": _editor_state(track_body),
    }
    validate(req, "AssistRequest")
    r = api.post("/assist", json=req)
    assert r.status_code == 200, r.text
    validate(r.json(), "AssistResponse", AssistResponse)
    assert_shape(r.json(), "assist")


@needs_writes
def test_stems_and_job(api: httpx.Client, track_body: dict[str, Any]) -> None:
    end = min(8.0, float(track_body["track"]["duration_s"]))
    r = api.post(f"/tracks/{track_body['track']['id']}/stems", json={"start_s": 0.0, "end_s": end})
    assert r.status_code == 200, r.text
    body = r.json()
    validate(body, "StemsResponse", models.StemsResponse)
    assert set(body) == {"job_id", "stems"}
    assert (body["job_id"] is None) != (body["stems"] is None), "exactly one of job_id / stems is set"
    assert_shape(body, "stems_ready" if body["stems"] is not None else "stems_queued")

    job_id = body["job_id"] or (None if LIVE else fixture("job_done_stems")["id"])
    if job_id is None:
        pytest.skip("stems already existed, so no job to poll")
    j = api.get(f"/jobs/{job_id}")
    assert j.status_code == 200, j.text
    job = j.json()
    validate(job, "Job", models.Job)
    expected = {"stems": "job_done_stems", "analyze": "job_done_analyze"}[job["kind"]]
    assert_shape(job, expected if job["output"] is not None else "job_running")


@fixture_mode_only
def test_analyze_job_fixture(api: httpx.Client) -> None:
    j = api.get(f"/jobs/{fixture('job_done_analyze')['id']}")
    assert j.status_code == 200, j.text
    validate(j.json(), "Job", models.Job)
    assert_shape(j.json(), "job_done_analyze")


@needs_writes
def test_import(api: httpx.Client) -> None:
    with FIXTURE_WAV.open("rb") as f:
        r = api.post("/imports", files={"file": ("contract.wav", f, "audio/wav")}, data={"session_id": SESSION})
    assert r.status_code == 200, r.text
    validate(r.json(), "ImportResponse", models.ImportResponse)
    assert_shape(r.json(), "import")


@needs_writes
def test_event(api: httpx.Client, search_body: dict[str, Any]) -> None:
    r = api.post(
        "/events",
        json={
            "session_id": SESSION,
            "query_id": search_body["query_id"],
            "window_id": search_body["results"][0]["window_id"],
            "action": "play",
        },
    )
    assert r.status_code == 204, r.text
    assert r.content == b""


# ---- error shapes (no state is created) ----


def test_unknown_route_is_not_found(api: httpx.Client) -> None:
    assert_error(api.get("/definitely-not-a-route"), 404, "not_found")


def test_bad_search_body_is_bad_request(api: httpx.Client) -> None:
    assert_error(api.post("/search", json={"limit": 999}), 400, "bad_request")


def test_stems_range_too_long(api: httpx.Client, track_body: dict[str, Any]) -> None:
    r = api.post(f"/tracks/{track_body['track']['id']}/stems", json={"start_s": 0.0, "end_s": 61.0})
    assert_error(r, 400, "range_too_long")


def test_unknown_job_is_not_found(api: httpx.Client) -> None:
    assert_error(api.get(f"/jobs/{uuid.uuid4()}"), 404, "not_found")


@live_only
def test_unknown_track_is_not_found(api: httpx.Client) -> None:
    assert_error(api.get("/tracks/jam_does_not_exist"), 404, "not_found")


@live_only
def test_unknown_window_why_is_not_found(api: httpx.Client) -> None:
    assert_error(api.post("/why", json={"window_id": "jam_does_not_exist:mix:0"}), 404, "not_found")


# ---- the shape checker itself ----


def test_same_shape_detects_differences() -> None:
    assert same_shape({"a": 1, "b": [{"x": 1}]}, {"a": 2, "b": [{"x": 5}]}) == []
    assert same_shape({"a": 1}, {"a": 1, "b": None}) == []  # null ≡ absent
    assert same_shape({"a": 1}, {"a": 1, "b": 0}) == ["$: extra keys [], missing keys ['b']"]
    assert same_shape({"a": 1, "c": "x"}, {"a": 1}) == ["$: extra keys ['c'], missing keys []"]
    assert same_shape({"b": [{"x": 1, "y": 2}]}, {"b": [{"x": 1}]}) == ["$.b[0]: extra keys ['y'], missing keys []"]
    ops = [{"op": "slice", "clip": "c1", "count": 4, "at": None, "snap": "beat"}, {"op": "reverse", "clip": "c1.4"}]
    assert same_shape([{"op": "reverse", "clip": "c1.2"}], ops) == []
    assert same_shape([{"op": "gain", "clip": "c1", "db": 3}], ops) == []  # no fixture partner → not compared
