"""Every CONTRACT §6 endpoint answers from fixtures with a body that validates against the contract models."""

import io

import pytest
from fastapi.testclient import TestClient

from app.main import app, fixture
from app.models.api import (
    ChipsResponse,
    ImportResponse,
    Job,
    SearchResponse,
    StemsResponse,
    TrackDetail,
    WhyResponse,
)
from app.models.ops import AssistResponse

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").json() == {"ok": True}


def test_chips() -> None:
    ChipsResponse.model_validate(client.get("/chips").json())


def test_search() -> None:
    r = client.post("/search", json={"text": "dusty soul keys", "chips": ["genre.soul"], "session_id": "s1"})
    assert r.status_code == 200
    body = SearchResponse.model_validate(r.json())
    assert len(body.results) == 8


def test_search_validation_error_shape() -> None:
    r = client.post("/search", json={"text": "x"})  # missing session_id
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


def test_track() -> None:
    tid = fixture("track_detail")["track"]["id"]
    TrackDetail.model_validate(client.get(f"/tracks/{tid}").json())


def test_stems_ready_and_range_too_long() -> None:
    tid = fixture("track_detail")["track"]["id"]
    ok = client.post(f"/tracks/{tid}/stems", json={"start_s": 0, "end_s": 10})
    assert StemsResponse.model_validate(ok.json()).stems
    bad = client.post(f"/tracks/{tid}/stems", json={"start_s": 0, "end_s": 61})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "range_too_long"


@pytest.mark.parametrize("name", ["job_done_stems", "job_done_analyze"])
def test_jobs(name: str) -> None:
    job = Job.model_validate(client.get(f"/jobs/{fixture(name)['id']}").json())
    assert job.status == "done"


def test_unknown_job_is_not_found() -> None:
    r = client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_import() -> None:
    r = client.post(
        "/imports",
        files={"file": ("loop.wav", io.BytesIO(b"RIFF"), "audio/wav")},
        data={"session_id": "s1"},
    )
    ImportResponse.model_validate(r.json())


def test_why() -> None:
    body = WhyResponse.model_validate(client.post("/why", json={"window_id": "fs_482913:mix:5000"}).json())
    assert body.window_id == "fs_482913:mix:5000"
    assert body.note == fixture("why")["note"]


def test_events() -> None:
    r = client.post("/events", json={"session_id": "s1", "window_id": "fs_482913:mix:0", "action": "play"})
    assert r.status_code == 204


def test_assist() -> None:
    req = {
        "messages": [{"role": "user", "content": "chop this into 4 and reverse the last one"}],
        "editor": {
            "bpm": 90,
            "clips": [
                {
                    "id": "c1",
                    "source": {
                        "track_id": "jam_1532881",
                        "audio_url": "/fixtures/audio/mix.wav",
                        "start_s": 0,
                        "end_s": 10.667,
                    },
                }
            ],
            "ops": [],
        },
    }
    r = client.post("/assist", json=req)
    assert r.status_code == 200
    assert AssistResponse.model_validate(r.json()).ops
