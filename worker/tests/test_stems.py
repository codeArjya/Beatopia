import contextlib
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
import soundfile as sf

from common import audio
from worker import handlers, jobs, main
from worker.engine import MODELS, SR, Engine


@pytest.mark.parametrize("start,end", [(-1, 10), (10, 10), (0, 61), (0, 101), (float("nan"), 1), (True, 1)])
def test_invalid_ranges(start, end):
    with pytest.raises(ValueError):
        handlers.bounds(dict(track_id="fs_1", start_s=start, end_s=end, model="htdemucs"), 100)


def test_unknown_models_and_outside_decoded_range():
    with pytest.raises(ValueError):
        handlers.bounds(dict(track_id="fs_1", start_s=0, end_s=1, model="fake"), 100)
    assert handlers.bounds(dict(track_id="fs_1", start_s=2, end_s=62, model="htdemucs_6s"), 100) == (
        2,
        62,
        "htdemucs_6s",
    )


@pytest.mark.parametrize("model", list(MODELS))
def test_engine_retries_cpu_once_and_preserves_model(monkeypatch, model):
    separator = object.__new__(Engine)
    separator.model, separator.device = model, "cpu"

    def broken(*_):
        raise RuntimeError("inference error")

    separator.separator = SimpleNamespace(separate_tensor=broken)
    calls = []

    def load(device):
        calls.append(device)
        return SimpleNamespace(separate_tensor=lambda y, sr: (y, {s: y / len(MODELS[model]) for s in MODELS[model]}))

    monkeypatch.setattr(separator, "load", load)
    result, timing = separator.separate(np.ones((100, 2), dtype=np.float32))
    assert calls == ["cpu"] and set(result) == set(MODELS[model])
    assert timing["fallback"] == "RuntimeError"
    monkeypatch.setattr(separator, "load", lambda _: SimpleNamespace(separate_tensor=broken))
    separator.separator = SimpleNamespace(separate_tensor=broken)
    with pytest.raises(RuntimeError):
        separator.separate(np.ones((100, 2), dtype=np.float32))
    with pytest.raises(ValueError):
        separator.separate(np.zeros((60 * SR + 1, 2), dtype=np.float32))


@pytest.fixture
def service(tmp_path, monkeypatch):
    t = np.arange(12 * SR) / SR
    signal = 0.2 * np.sin(2 * np.pi * np.where(t < 6, 440, 880) * t)
    sf.write(tmp_path / "source.wav", np.column_stack([signal, signal]), SR)
    audio.to_mp3(str(tmp_path / "source.wav"), str(tmp_path / "source.mp3"))
    objects = {"tracks/fs_1/mix.mp3": (tmp_path / "source.mp3").read_bytes()}
    rows, staged, calls = [], [], []
    state = dict(fail_upload=False, fail_db=False)

    class Connection:
        def execute(self, sql, params):
            if "SELECT stem,range" in sql:
                tid, model, start, end = params
                return SimpleNamespace(
                    fetchall=lambda: [
                        (r[1], r[2], r[3], r[4])
                        for r in rows
                        if r[0] == tid and r[5] == model and r[2] <= start and r[3] >= end
                    ]
                )
            if "SELECT 1 FROM stems" in sql:
                return SimpleNamespace(fetchone=lambda: None)
            if "INSERT INTO stems" in sql:
                if state["fail_db"]:
                    raise RuntimeError("db failed")
                staged.append(params)
            return SimpleNamespace(fetchone=lambda: None)

    @contextlib.contextmanager
    def connect():
        try:
            yield Connection()
            for row in staged:
                rows[:] = [r for r in rows if r[:4] != row[:4]]
                rows.append(row)
        finally:
            staged.clear()

    def upload(local, path, content_type):
        if state["fail_upload"]:
            raise RuntimeError("upload failed")
        objects[path] = Path(local).read_bytes()

    client_type = httpx.Client

    def client(**kwargs):
        def respond(request):
            key = request.url.path.lstrip("/")
            return httpx.Response(200 if key in objects else 404, content=objects.get(key, b""))

        return client_type(transport=httpx.MockTransport(respond), **kwargs)

    def separate(y):
        calls.append(y.copy())
        return {s: y / 4 for s in MODELS["htdemucs"]}, {"device": "cpu", "inference_s": 0}

    monkeypatch.setattr(handlers, "track_lock", lambda _: contextlib.nullcontext())
    monkeypatch.setattr(handlers, "read_track", lambda _: dict(duration_s=12, audio_path="tracks/fs_1/mix.mp3"))
    monkeypatch.setattr(handlers.db, "connect", connect)
    monkeypatch.setattr(handlers.storage, "upload", upload)
    monkeypatch.setattr(handlers.storage, "public_url", lambda p: "https://audio.example/" + p)
    monkeypatch.setattr(handlers.httpx, "Client", client)
    monkeypatch.setattr(
        handlers,
        "engine",
        lambda _: SimpleNamespace(
            identity={"model": "htdemucs", "weights": "offline-test"}, load_s=0, separate=separate
        ),
    )
    return SimpleNamespace(root=tmp_path / "worker", rows=rows, calls=calls, state=state, objects=objects)


@pytest.mark.parametrize("failure", ["fail_upload", "fail_db"])
def test_resume_after_failure_and_covering_cache(service, failure):
    data = dict(track_id="fs_1", start_s=6, end_s=12, model="htdemucs")
    service.state[failure] = True
    with pytest.raises(RuntimeError):
        handlers.stems_job(data, service.root, lambda _: None, {})
    assert service.rows == [] and len(service.calls) == 1
    service.state[failure] = False
    progress, timings = [], {}
    result = handlers.stems_job(data, service.root, progress.append, timings)
    assert timings["separation_reused"] and len(service.calls) == 1 and len(service.rows) == 4
    assert progress == sorted(progress) and progress[-1] < 1
    assert all(
        s["range_start_s"] == 6 and s["range_end_s"] == 12 and "_6000_12000.mp3" in s["url"] for s in result["stems"]
    )
    # The actual decoded crop contains the second tone, not the beginning of the mix.
    y = service.calls[0][:, 0]
    frequency = np.argmax(abs(np.fft.rfft(y))) * SR / len(y)
    assert frequency == pytest.approx(880, abs=1)
    timings = {}
    reused = handlers.stems_job({**data, "start_s": 7, "end_s": 10}, service.root, lambda _: None, timings)
    assert reused == result and timings["covering_cache_reused"] and len(service.calls) == 1
    for stem in reused["stems"]:
        # Requested 7s corresponds to local 1s in a file covering [6,12].
        assert 7 - stem["range_start_s"] == 1


def test_corrupt_public_cache_is_repaired(service):
    data = dict(track_id="fs_1", start_s=6, end_s=12, model="htdemucs")
    handlers.stems_job(data, service.root, lambda _: None, {})
    service.objects["tracks/fs_1/stems/bass_6000_12000.mp3"] = b"broken"
    timings = {}
    handlers.stems_job(data, service.root, lambda _: None, timings)
    assert timings["separation_reused"] and len(service.calls) == 1
    assert service.objects["tracks/fs_1/stems/bass_6000_12000.mp3"] != b"broken"


def test_partial_stem_rows_do_not_count_as_covering_cache(service):
    data = dict(track_id="fs_1", start_s=6, end_s=12, model="htdemucs")
    handlers.stems_job(data, service.root, lambda _: None, {})
    service.rows.pop()
    timings = {}
    handlers.stems_job(data, service.root, lambda _: None, timings)
    assert "covering_cache_reused" not in timings and timings["separation_reused"]
    assert len(service.rows) == 4 and len(service.calls) == 1


def test_processing_failure_terminates_and_progress_rejects_nan(tmp_path, monkeypatch):
    terminal = []
    monkeypatch.setattr(main, "terminate", lambda *a, **kw: terminal.append(kw))
    monkeypatch.setattr(handlers, "stems_job", lambda *_: (_ for _ in ()).throw(RuntimeError("secret URL")))
    main.run_job(dict(id="test", kind="stems", input={}), tmp_path)
    assert len(terminal) == 1 and "error" in terminal[0] and "secret" not in terminal[0]["error"]
    assert json_status(tmp_path) == "error"
    for value in (float("nan"), -0.1, 1):
        with pytest.raises(ValueError):
            jobs.progress("test", value)


def json_status(root):
    import json

    return json.loads((root / "worker.jsonl").read_text())["status"]
