import copy
import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
import soundfile as sf
import torch

from common import analysis
from ingest import heroes
from ingest.separation import SR, STEMS, Engine, encode
from ingest.sources import write_json


def test_rank_reserves_thirty_and_breaks_ties_by_id():
    rows = [dict(id=f"fs_{i:03}", duration_s=10, loopability=0.5, tags=["piano"]) for i in range(35)]
    rows += [dict(id=f"fs_x{i}", duration_s=10, loopability=1, tags=["drum loop", "kick"]) for i in range(60)]
    selected, audit = heroes.ranked(list(reversed(rows)), 80)
    assert len(selected) == len({r["id"] for r in selected}) == 80
    assert all(r["required_tags"] == ["piano"] for r in selected[:30])
    assert selected[0]["id"] == "fs_000"
    assert audit["reserved"] == 30 and audit["audibly_verified"] == 0
    assert audit["tag_shortfall"] == 0
    assert selected[0]["score"] == pytest.approx(0.5 / 120)
    assert all(r["listening"] == "unreviewed" for r in selected)


def test_rank_shortfall_is_explicit_and_unknown_tags_do_not_inflate_score():
    selected, audit = heroes.ranked([dict(id="fs_1", duration_s=10, loopability=0, tags=["piano", "fake"])], 80)
    assert selected[0]["score"] == 0
    assert selected[0]["tags"] == ["piano"]
    assert audit["tag_shortfall"] == 29


def test_engine_bounds_and_invalid_outputs():
    engine = object.__new__(Engine)
    engine.device = "cpu"
    with pytest.raises(ValueError, match="at most 180"):
        engine.separate(np.zeros((1, 1), dtype=np.float32))
    engine.separator = SimpleNamespace(separate_tensor=lambda *_: (None, {"drums": torch.zeros((2, 10))}))
    with pytest.raises(ValueError, match="four-stem"):
        engine.separate(np.zeros((10, 2), dtype=np.float32))


def test_engine_accelerator_error_retries_cpu_once(monkeypatch):
    engine = object.__new__(Engine)
    engine.device = "mps"

    def broken(*_):
        raise RuntimeError("accelerator unavailable")

    engine.separator = SimpleNamespace(separate_tensor=broken)
    calls = []

    def load(device):
        calls.append(device)
        return SimpleNamespace(separate_tensor=lambda y, _: (y, {s: y / 4 for s in STEMS}))

    monkeypatch.setattr(engine, "_load", load)
    arrays, timing = engine.separate(np.ones((10, 2), dtype=np.float32))
    assert calls == ["cpu"] and timing["device"] == "cpu" and timing["fallback"] == "RuntimeError"
    assert set(arrays) == set(STEMS)


@pytest.fixture
def hero_cache(tmp_path):
    y = np.column_stack([0.1 * np.sin(2 * np.pi * 440 * np.arange(6 * SR) / SR)] * 2).astype(np.float32)
    tid = "jam_42"
    directory = tmp_path / tid
    directory.mkdir()
    windows = []
    for stem in STEMS:
        encode(y, directory / f"{stem}.mp3")
        windows.append(
            dict(
                id=f"{tid}:{stem}:0",
                stem=stem,
                start_s=0,
                end_s=6,
                rms=0.1,
                loopability=0,
                density=0.5,
                tags=["piano"],
                tag_scores={"piano": 0.5},
            )
        )
    vectors = np.zeros((4, 512), dtype=np.float32)
    vectors[:, 0] = 1
    manifest = dict(
        identity={"test": "identity"},
        windows=windows,
        hashes={s: hashlib.sha256((directory / f"{s}.mp3").read_bytes()).hexdigest() for s in STEMS},
    )
    np.savez_compressed(directory / "features.npz", embeddings=vectors)
    write_json(directory / "manifest.json", manifest)
    mix = dict(id=tid, duration_s=6, offsets=[dict(processed_start_s=0, processed_end_s=6)])
    return tmp_path, directory, mix, manifest, vectors


@pytest.mark.parametrize("mutation", ["vector", "hash", "range", "join", "missing", "fingerprint", "nan"])
def test_cache_rejects_invalid_stages(hero_cache, mutation):
    _, directory, mix, manifest, vectors = hero_cache
    if mutation == "vector":
        np.savez_compressed(directory / "features.npz", embeddings=vectors * 2)
    elif mutation == "hash":
        (directory / "bass.mp3").write_bytes(b"corrupt")
    elif mutation == "range":
        manifest["windows"][0]["end_s"] = 7
    elif mutation == "join":
        mix["offsets"] = [dict(processed_end_s=3), dict(processed_end_s=6)]
    elif mutation == "missing":
        manifest["windows"] = manifest["windows"][1:]
        np.savez_compressed(directory / "features.npz", embeddings=vectors[1:])
    elif mutation == "fingerprint":
        manifest["identity"] = {"test": "wrong"}
    else:
        manifest["windows"][0]["tag_scores"]["piano"] = float("nan")
    write_json(directory / "manifest.json", manifest)
    with pytest.raises(ValueError):
        heroes.cached(directory, {"test": "identity"}, mix)


def test_four_stems_decode_and_cache_validate(hero_cache):
    _, directory, mix, manifest, vectors = hero_cache
    actual, embeddings = heroes.cached(directory, manifest["identity"], mix)
    assert actual == manifest and np.array_equal(vectors, embeddings)
    for s in STEMS:
        info = sf.info(directory / f"{s}.mp3")
        assert info.samplerate == 44100 and info.channels == 2 and info.duration == 6


@pytest.mark.parametrize("stage", ["upload", "db"])
def test_publication_failure_rolls_back_and_resume_is_idempotent(hero_cache, monkeypatch, stage):
    root, directory, mix, manifest, vectors = hero_cache
    staged, committed = [], []
    fail = [True]
    uploads = []

    class Connection:
        def execute(self, sql, params):
            staged.append(sql)
            if stage == "db" and fail[0] and "INSERT INTO windows" in sql:
                raise RuntimeError("interrupted DB publication")

    @contextmanager
    def connect():
        try:
            yield Connection()
            committed.extend(staged)
        finally:
            staged.clear()

    def upload(local, *_):
        uploads.append(local)
        if stage == "upload" and fail[0] and len(uploads) == 2:
            raise RuntimeError("interrupted upload")

    monkeypatch.setattr(heroes.db, "connect", connect)
    monkeypatch.setattr(heroes.storage, "upload", upload)
    monkeypatch.setattr(heroes.storage, "public_url", lambda p: f"https://audio.example/{p}")
    monkeypatch.setattr(heroes, "verify", lambda *_: bool(committed))

    def respond(request):
        return httpx.Response(200, content=(directory / request.url.path.split("/")[-1]).read_bytes())

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(RuntimeError):
            heroes.publish(root, mix, manifest, vectors, client)
        assert not committed
        fail[0] = False
        assert heroes.publish(root, mix, manifest, vectors, client) == "published"
        count, upload_count = len(committed), len(uploads)
        assert sum("UPDATE tracks SET is_hero=true" in s for s in committed) == 1
        assert heroes.publish(root, mix, manifest, vectors, client) == "verified_existing"
        assert len(committed) == count and len(uploads) == upload_count


def test_stem_features_never_cross_excerpt_join(monkeypatch):
    y = np.ones((16 * SR, 2), dtype=np.float32) * 0.1
    arrays = {s: y.copy() for s in STEMS}
    mix = dict(
        id="jam_1",
        offsets=[dict(processed_start_s=0, processed_end_s=10), dict(processed_start_s=10, processed_end_s=16)],
    )
    monkeypatch.setattr(analysis, "analyze_track", lambda y, sr: analysis.TrackFeatures(len(y) / sr, None, None, []))
    monkeypatch.setattr(heroes.clap, "embed_audio", lambda chunks, sr: np.tile(np.eye(1, 512), (len(chunks), 1)))
    monkeypatch.setattr(analysis, "zero_shot_tags", lambda e: [(["piano"], {"piano": 0.3}) for _ in e])
    windows, vectors = heroes.features(mix, arrays)
    assert set(w["stem"] for w in windows) == set(STEMS)
    assert all(not w["start_s"] < 10 < w["end_s"] for w in windows)
    assert all(0.5 <= w["density"] <= 1 for w in windows)
    assert vectors.shape == (len(windows), 512)
    arrays["vocals"][:] = 0
    with pytest.raises(ValueError, match="no audible"):
        heroes.features(mix, arrays)


def test_raw_checkpoint_resumes_without_inference(hero_cache, monkeypatch):
    root, directory, mix, manifest, vectors = hero_cache
    mix = {**mix, "audio_sha256": "mix-hash"}
    identity = dict(
        mix_sha256="mix-hash", pipeline=heroes.fingerprint(), separation={"model": "test"}, hero_pipeline="1"
    )
    write_json(
        directory / "separated.json", dict(identity=identity, hashes=manifest["hashes"], timing={"inference_s": 5})
    )
    (directory / "manifest.json").unlink()
    monkeypatch.setattr(heroes, "load_mix", lambda *_: (mix, directory / "unused-mix.mp3"))
    monkeypatch.setattr(heroes, "features", lambda *_: (copy.deepcopy(manifest["windows"]), vectors))
    engine = SimpleNamespace(identity={"model": "test"}, separate=lambda *_: pytest.fail("repeated inference"))
    _, result, actual = heroes.prepare(root, root, mix["id"], engine)
    assert result["timing"]["inference_s"] == 5 and np.array_equal(actual, vectors)
    assert json.loads((directory / "manifest.json").read_text())["identity"] == identity


def test_batch_uses_spares_without_lowering_completion_target(tmp_path, monkeypatch):
    def audit(root, limit):
        write_json(root / "audit.json", {"ranking": [{"id": s} for s in ("bad", "good1", "good2")]})
        return [{"id": "bad"}, {"id": "good1"}]

    seen = []

    def prepare(data, root, tid, engine):
        seen.append(tid)
        if tid == "bad":
            raise ValueError("silent vocals")
        return {}, {"windows": [1], "timing": {"inference_s": 1}}, np.zeros((1, 512))

    monkeypatch.setattr(heroes, "Engine", lambda: SimpleNamespace(device="cpu", load_s=0, identity={}))
    monkeypatch.setattr(heroes, "audit", audit)
    monkeypatch.setattr(heroes, "prepare", prepare)
    monkeypatch.setattr(heroes, "publish", lambda *_: "published")
    # Retain the failed attempt in exit status even when spares satisfy the target.
    with pytest.raises(SystemExit):
        heroes.run(tmp_path, tmp_path, 2, "batch", None)
    assert seen == ["bad", "good1", "good2"]
    events = [json.loads(line) for line in (tmp_path / "heroes.log").read_text().splitlines()]
    assert events[-1] == {**events[-1], "event": "finished", "completed": 2, "failed": 1, "target": 2}
    assert json.loads((tmp_path / "queue.json").read_text()) == ["bad", "good1", "good2"]


def test_single_hero_does_not_overwrite_batch_queue(tmp_path, monkeypatch):
    write_json(tmp_path / "queue.json", ["batch1", "batch2"])
    monkeypatch.setattr(heroes, "Engine", lambda: SimpleNamespace(device="cpu", load_s=0, identity={}))
    seen = []

    def prepare(data, root, tid, engine):
        seen.append(tid)
        return {}, {"windows": [], "timing": {}}, np.zeros((0, 512))

    monkeypatch.setattr(heroes, "prepare", prepare)
    monkeypatch.setattr(heroes, "publish", lambda *_: "verified_existing")
    heroes.run(tmp_path, tmp_path, 1, "batch", "single")
    assert seen == ["single"]
    assert json.loads((tmp_path / "queue.json").read_text()) == ["batch1", "batch2"]


def test_verify_mode_never_recomputes_or_publishes(tmp_path, monkeypatch):
    monkeypatch.setattr(heroes, "Engine", lambda: SimpleNamespace(device="cpu", load_s=0, identity={}))
    monkeypatch.setattr(heroes, "load_mix", lambda *_: ({"audio_sha256": "mix"}, None))
    monkeypatch.setattr(heroes, "cached", lambda *_: ({"windows": []}, np.zeros((0, 512))))
    monkeypatch.setattr(heroes, "verify", lambda *_: True)
    monkeypatch.setattr(heroes, "prepare", lambda *_: pytest.fail("read-only verifier recomputed features"))
    monkeypatch.setattr(heroes, "publish", lambda *_: pytest.fail("read-only verifier mutated DB"))
    heroes.run(tmp_path, tmp_path, 1, "verify", "jam_1")
