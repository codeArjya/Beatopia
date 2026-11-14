import copy
import hashlib
from contextlib import contextmanager

import httpx
import numpy as np
import pytest
import soundfile as sf

from common import analysis
from ingest import pipeline, run
from ingest.sources import Discovery, candidate, cc_license


@pytest.fixture
def item():
    return candidate(
        {
            "id": 42,
            "name": "Loop",
            "username": "Artist",
            "duration": 16,
            "license": "https://creativecommons.org/licenses/by/4.0/",
            "url": "https://freesound.org/s/42/",
            "previews": {"preview-hq-mp3": "https://cdn.example/42.mp3"},
        },
        "freesound",
    )


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
        ("http://creativecommons.org/licenses/by-sa/3.0/", "CC-BY-SA-3.0"),
    ],
)
def test_jamendo_eligible(url, expected):
    row = {
        "id": 1,
        "name": "Song",
        "artist_name": "Artist",
        "duration": 300,
        "license_ccurl": url,
        "audiodownload_allowed": True,
        "audiodownload": "https://cdn.example/song.mp3",
        "shareurl": "https://jamendo.com/t/1",
    }
    assert candidate(row, "jamendo").license == expected
    for change in (
        {"audiodownload_allowed": False},
        {"audiodownload_allowed": "true"},
        {"audiodownload": ""},
        {"artist_name": ""},
    ):
        with pytest.raises(ValueError):
            candidate({**row, **change}, "jamendo")


@pytest.mark.parametrize("path", ["by-nc/4.0", "by-nd/3.0", "by-nc-sa/4.0", "by/4.0/deed.en"])
def test_reject_restrictive_or_unrecognized_licenses(path):
    with pytest.raises(ValueError):
        cc_license(f"https://creativecommons.org/licenses/{path}/", jamendo=True)
    with pytest.raises(ValueError):
        cc_license("https://creativecommons.org.evil/licenses/by/4.0/", jamendo=True)


def test_cached_discovery_and_request_budget(tmp_path, monkeypatch):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr("ingest.sources.time.sleep", lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        discovery = Discovery(tmp_path, client, {"freesound": "secret"})
        assert discovery.request("freesound", {"query": "piano"}) == {"results": []}
        discovery.request("freesound", {"query": "piano"})
        assert len(calls) == 1
        assert "secret" not in "".join(p.read_text() for p in tmp_path.rglob("*.json"))
        discovery.budget["freesound"]["total"] = 600
        with pytest.raises(RuntimeError, match="budget"):
            discovery.request("freesound", {"query": "new"})


def test_corrupt_download_is_never_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    attempts = []

    def respond(request):
        attempts.append(1)
        return httpx.Response(200, content=b"corrupt audio")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError):
            pipeline.download(client, "https://cdn.example/input", tmp_path / "original.audio")
    assert len(attempts) == 3
    assert not list(tmp_path.iterdir())


def test_prepare_long_audio_join_playback_and_cached_resume(tmp_path, item, monkeypatch):
    # Real FFmpeg encode/decode, synthetic audio; CLAP replaced only in this offline test.
    sr = pipeline.SR
    t = np.arange(sr * 400) / sr
    y = 0.15 * np.sin(2 * np.pi * np.where(t < 140, 440, 880) * t)
    sf.write(tmp_path / "original.audio", np.column_stack([y, y * 0.5]), sr, format="WAV")
    monkeypatch.setattr(analysis, "analyze_track", lambda y, sr: analysis.TrackFeatures(len(y) / sr, None, None, []))

    def embeddings(chunks, sr):
        vectors = np.zeros((len(chunks), 512), dtype=np.float32)
        vectors[:, 0] = 1
        return vectors

    monkeypatch.setattr(pipeline.clap, "embed_audio", embeddings)
    monkeypatch.setattr(analysis, "zero_shot_tags", lambda e: [(["tone"], {"tone": 0.5}) for _ in e])
    with httpx.Client() as client:
        manifest = pipeline.prepare(item, tmp_path, client)
        assert manifest["duration_s"] == pytest.approx(180, abs=0.01)
        assert manifest["offsets"] == [
            {"source_start_s": 0, "source_end_s": 120, "processed_start_s": 0, "processed_end_s": 120},
            {"source_start_s": 170, "source_end_s": 230, "processed_start_s": 120, "processed_end_s": 180},
        ]
        assert all(not w["start_s"] < 120 < w["end_s"] for w in manifest["windows"])
        decoded, _ = pipeline.audio.load_mono(str(tmp_path / "mix.mp3"))
        assert len(decoded) / sr == manifest["duration_s"]
        assert sf.info(tmp_path / "mix.mp3").channels == 2
        # Source 195s appears at processed 145s; inspect content, not just metadata.
        sample = decoded[145 * sr : 146 * sr]
        peak = np.argmax(abs(np.fft.rfft(sample)))
        assert peak == pytest.approx(880, abs=1)
        monkeypatch.setattr(pipeline.clap, "embed_audio", lambda *_: pytest.fail("recomputed cached embeddings"))
        assert pipeline.prepare(item, tmp_path, client) == manifest
        # Broken derived embeddings are rebuilt from the cached original with the same fingerprint.
        (tmp_path / "features.npz").write_bytes(b"broken compressed features")
        monkeypatch.setattr(pipeline.clap, "embed_audio", embeddings)
        assert pipeline.prepare(item, tmp_path, client) == manifest
        (tmp_path / "mix.mp3").write_bytes(b"broken")
        with pytest.raises(ValueError, match="hash"):
            pipeline.validate(manifest, tmp_path)


@pytest.fixture
def cached(tmp_path, item):
    (tmp_path / "mix.mp3").write_bytes(b"verified-public-audio")
    vectors = np.zeros((1, 512), dtype=np.float32)
    vectors[0, 0] = 1
    np.savez_compressed(tmp_path / "features.npz", embeddings=vectors)
    manifest = {
        "id": item.id,
        "duration_s": 16,
        "bpm": None,
        "key": None,
        "beat_times": [],
        "attribution": "Artist CC-BY-4.0",
        "offsets": [{"processed_end_s": 16}],
        "audio_sha256": hashlib.sha256((tmp_path / "mix.mp3").read_bytes()).hexdigest(),
        "windows": [
            {
                "id": "fs_42:mix:0",
                "start_s": 0,
                "end_s": 10,
                "loopability": 0,
                "rms": 0.1,
                "density": 0.5,
                "tags": ["tone"],
                "tag_scores": {"tone": 0.5},
            }
        ],
    }
    return manifest


@pytest.mark.parametrize("stage", ["upload", "db"])
def test_partial_failure_resume_transaction(tmp_path, item, cached, monkeypatch, stage):
    committed, staged, uploads = [], [], []
    fail = [True]

    class Connection:
        def execute(self, sql, params):
            staged.append(sql)
            if stage == "db" and fail[0] and sql.lstrip().startswith("INSERT INTO windows"):
                raise RuntimeError("simulated DB failure")

    @contextmanager
    def connect():
        try:
            yield Connection()
            committed.extend(staged)
        finally:
            staged.clear()

    def upload(*_):
        uploads.append(1)
        if stage == "upload" and fail[0]:
            raise RuntimeError("simulated partial upload")

    monkeypatch.setattr(pipeline, "published", lambda *_: bool(committed))
    monkeypatch.setattr(pipeline.db, "connect", connect)
    monkeypatch.setattr(pipeline.storage, "upload", upload)
    monkeypatch.setattr(pipeline.storage, "public_url", lambda _: "https://storage.example/audio")
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"verified-public-audio"))
    ) as c:
        with pytest.raises(RuntimeError):
            pipeline.publish(item, cached, tmp_path, c)
        assert not committed
        fail[0] = False
        assert pipeline.publish(item, cached, tmp_path, c) == "published"
        count = len(committed)
        assert pipeline.publish(item, cached, tmp_path, c) == "verified_existing"
        assert len(committed) == count
        assert len(uploads) == 2


@pytest.mark.parametrize("mutation", ["range", "join", "attribution", "vector"])
def test_invalid_artifacts_rejected(tmp_path, cached, mutation):
    m = copy.deepcopy(cached)
    if mutation == "range":
        m["windows"][0]["end_s"] = 17
    elif mutation == "join":
        m["offsets"] = [{"processed_end_s": 5}]
    elif mutation == "attribution":
        m["attribution"] = ""
    else:
        np.savez(tmp_path / "features.npz", embeddings=np.zeros((1, 512)))
    with pytest.raises(ValueError):
        pipeline.validate(m, tmp_path)


def test_missing_jamendo_key_falls_back(tmp_path, item, monkeypatch):
    monkeypatch.delenv("JAMENDO_CLIENT_ID", raising=False)
    calls = []

    def discover(self, source, count):
        calls.append((source, count))
        return [item]

    monkeypatch.setattr(Discovery, "discover", discover)
    monkeypatch.setattr(run, "process", lambda *_: "published")
    run.run(tmp_path, "jamendo", 1)
    assert calls == [("freesound", 6)]
    assert '"event": "fallback"' in (tmp_path / "ingest.log").read_text()


@pytest.mark.parametrize("limit", ["0", "401", "-1"])
def test_cli_ceiling(limit):
    with pytest.raises(SystemExit) as error:
        run.main(["--limit", limit])
    assert error.value.code == 2


def test_retry_after_is_durable_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr("ingest.sources.time.sleep", lambda _: None)
    calls = []

    def respond(request):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "3600"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        d = Discovery(tmp_path, client, {"freesound": "key"})
        with pytest.raises(RuntimeError, match="cooldown"):
            d.request("freesound", {"query": "x"})
        resumed = Discovery(tmp_path, client, {"freesound": "key"})
        with pytest.raises(RuntimeError, match="cooldown"):
            resumed.request("freesound", {"query": "x"})
        assert len(calls) == 1


@pytest.mark.parametrize("damage", ["missing", "vector", "tags", "public"])
def test_published_rechecks_database_and_storage(tmp_path, cached, monkeypatch, damage):
    vectors = pipeline.validate(cached, tmp_path)

    class Vector:
        def to_numpy(self):
            return -vectors[0] if damage == "vector" else vectors[0]

    rows = [("fs_42:mix:0", Vector(), 0, 10, [] if damage == "tags" else ["tone"], {"tone": 0.5}, 0, 0.1, 0.5)]

    class Cursor:
        def fetchone(self):
            return (16, cached["attribution"], "tracks/fs_42/mix.mp3")

        def fetchall(self):
            return [] if damage == "missing" else rows

    class Connection:
        def execute(self, *_):
            return Cursor()

    @contextmanager
    def connect():
        yield Connection()

    monkeypatch.setattr(pipeline.db, "connect", connect)
    monkeypatch.setattr(pipeline.storage, "public_url", lambda _: "https://storage.example/audio")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as c:
        assert not pipeline.published(cached, c, vectors)
