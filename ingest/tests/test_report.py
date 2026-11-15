import copy
import json

import httpx
import numpy as np
import pytest
import soundfile as sf

from common import audio
from ingest import report


def window() -> dict:
    return dict(
        id="fs_1:mix:0",
        track_id="fs_1",
        stem="mix",
        start_s=0,
        end_s=10,
        rms=0.1,
        density=0.2,
        loopability=0.3,
        tags=["piano"],
        tag_scores={"piano": 0.4},
        embedding=np.eye(1, 512, dtype=np.float32)[0],
    )


@pytest.mark.parametrize("damage", ["vector", "range", "scores", "tags", "density", "id"])
def test_reject_invalid_database_windows(damage):
    w = window()
    assert report.window_issues(w, {"duration_s": 10}, {"piano"}) == []
    if damage == "vector":
        w["embedding"] *= 2
    elif damage == "range":
        w["end_s"] = 11
    elif damage == "scores":
        w["tag_scores"] = {"piano": float("nan")}
    elif damage == "tags":
        w["tags"] = ["invented"]
    elif damage == "density":
        w["density"] = -1
    else:
        w["id"] = "wrong"
    assert report.window_issues(w, {"duration_s": 10}, {"piano"})


def test_cached_comparison_catches_missing_and_changed_values():
    w = window()
    report.compare_windows([w], w["embedding"][None], [w])
    with pytest.raises(ValueError, match="set"):
        report.compare_windows([w], w["embedding"][None], [])
    changed = copy.deepcopy(w)
    changed["tag_scores"]["piano"] = 0.5
    with pytest.raises(ValueError, match="values"):
        report.compare_windows([w], w["embedding"][None], [changed])


def test_range_stems_do_not_satisfy_full_hero():
    track = {"id": "fs_1", "duration_s": 60}
    rows = [
        dict(stem=s, range_start_s=0, range_end_s=30, path=f"tracks/fs_1/stems/{s}.mp3", model="htdemucs")
        for s in report.STEMS
    ]
    assert not report.full_stems(track, rows)
    for row in rows:
        row["range_end_s"] = 60
    assert report.full_stems(track, rows)
    rows.pop()
    assert not report.full_stems(track, rows)


@pytest.fixture
def public_mp3(tmp_path):
    sr = 44100
    wav, mp3 = tmp_path / "mix.wav", tmp_path / "mix.mp3"
    sf.write(wav, np.sin(np.arange(sr * 4) * 2 * np.pi * 440 / sr) * 0.1, sr)
    audio.to_mp3(str(wav), str(mp3))
    return mp3


@pytest.mark.parametrize("damage", [None, "hash", "duration", "corrupt", "missing"])
def test_public_bytes_are_decoded_and_streams_probed(public_mp3, monkeypatch, damage):
    monkeypatch.setenv("SUPABASE_URL", "https://example.test")
    content = public_mp3.read_bytes()
    spec = dict(
        path="tracks/fs_1/mix.mp3",
        track_id="fs_1",
        duration_s=4,
        sha256=report.hashlib.sha256(content).hexdigest(),
        local=str(public_mp3),
    )
    if damage == "hash":
        spec["sha256"] = "bad"
    elif damage == "duration":
        spec["duration_s"] = 7
    elif damage == "corrupt":
        content = b"not audio"
        spec.pop("sha256")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404 if damage == "missing" else 200, content=content)
        )
    ) as client:
        result = report.public_object(spec, client)
    assert result["verified"] is (damage is None)
    if damage is None:
        assert result["sample_rate"] == 44100
        assert result["channels"] == 2
        assert result["streams"][0]["codec_name"] == "mp3"
    assert "example.test" not in json.dumps(result)


def test_small_corpus_does_not_claim_targets_or_listening(tmp_path, monkeypatch):
    monkeypatch.setattr(report.analysis, "_vocab", lambda: {"instrument": ["piano"]})
    w = window()
    track = dict(
        id="fs_1",
        duration_s=10,
        source="freesound",
        source_id="1",
        license="CC0",
        title="Piano",
        artist="Artist",
        attribution="Credit",
        is_hero=False,
        audio_path="tracks/fs_1/mix.mp3",
    )
    imported = {**track, "id": "imp_1", "source": "import"}
    data = dict(
        tracks=[track, imported],
        windows=[w],
        stems=[],
        jobs=[dict(id="unknown", status="error"), dict(id="6f6623b3-35f6-4e82-88f7-46f4d5f557e9", status="error")],
    )
    (tmp_path / "queue.json").write_text(json.dumps([dict(source="freesound", source_id="2")]))
    result, specs = report.build_report(data, tmp_path)
    assert result["counts"]["library_tracks"] == 1
    assert result["counts"]["imports"] == 1
    assert len(result["random_windows"]) == 1
    assert result["tags"]["piano"]["tracks"] == 1
    assert result["track_audit"][0]["issues"]  # Missing manifest is not a passing track.
    assert result["missing_stages"][0]["id"] == "fs_2"
    assert [j["classification"] for j in result["jobs"]["errors"]] == [
        "operational_unexplained",
        "intentional_session4_acceptance",
    ]
    report.finish_report(result, [{**specs[0], "verified": False}])
    assert result["acceptance"]["technically_verified_library"] == 0
    assert not result["acceptance"]["heroes_80"]
    assert result["acceptance"]["prominent_timbres_30"] == "unverified"


def api_track(**over) -> dict:
    """What WS2's fallback.store_track inserts before a stems request (CONTRACT §7.7)."""
    track = dict(
        id="fs_754932",
        source="freesound",
        source_id="754932",
        source_url="https://freesound.org/s/754932/",
        title="Kazoo",
        artist="someone",
        license="CC0",
        attribution="Kazoo by someone; https://freesound.org/s/754932/; CC0",
        duration_s=11.0,
        bpm=None,
        key=None,
        beat_times=[],
        is_hero=False,
        audio_path="tracks/fs_754932/mix.mp3",
    )
    return {**track, **over}


def stem_rows(tid: str, end: float) -> list[dict]:
    return [
        dict(track_id=tid, stem=s, range_start_s=0, range_end_s=end, path=f"tracks/{tid}/stems/{s}_0_11000.mp3")
        for s in report.STEMS
    ]


def test_api_materialized_fallback_track_is_audited_without_a_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(report.analysis, "_vocab", lambda: {"instrument": ["piano"]})
    data = dict(tracks=[api_track()], windows=[], stems=stem_rows("fs_754932", 11.0), jobs=[])
    result, specs = report.build_report(data, tmp_path)
    assert result["counts"]["library_tracks"] == 0 and result["counts"]["api_materialized_tracks"] == 1
    assert result["counts"]["imports"] == 0
    assert result["track_audit"] == []  # not an ingested library track: no manifest expected
    assert result["api_materialized_audit"] == [{"id": "fs_754932", "stems": 4, "issues": []}]
    # Its public mix and stems are still decoded and probed like every other object.
    assert {s["path"] for s in specs} == {"tracks/fs_754932/mix.mp3", *(r["path"] for r in data["stems"])}
    report.finish_report(result, [{**s, "verified": True} for s in specs])
    assert result["acceptance"]["technically_verified_library"] == 0  # never counts toward the 300-500 target


@pytest.mark.parametrize(
    ("over", "issue"),
    [
        (dict(attribution=" "), "attribution"),
        (dict(license="CC-BY-NC-4.0"), "license"),
        (dict(source_id="1"), "id_source_mismatch"),
        (dict(audio_path="tracks/fs_754932/preview.mp3"), "audio_path"),
    ],
)
def test_api_materialized_metadata_problems_are_issues(tmp_path, monkeypatch, over, issue):
    monkeypatch.setattr(report.analysis, "_vocab", lambda: {"instrument": ["piano"]})
    result, _ = report.build_report(dict(tracks=[api_track(**over)], windows=[], stems=[], jobs=[]), tmp_path)
    assert issue in result["api_materialized_audit"][0]["issues"]


def test_api_materialized_bad_stem_range_is_an_issue(tmp_path, monkeypatch):
    monkeypatch.setattr(report.analysis, "_vocab", lambda: {"instrument": ["piano"]})
    data = dict(tracks=[api_track()], windows=[], stems=stem_rows("fs_754932", 30.0), jobs=[])
    result, _ = report.build_report(data, tmp_path)
    assert "invalid_stem_range_or_name" in result["api_materialized_audit"][0]["issues"]


@pytest.mark.parametrize("over", [dict(bpm=90.0), dict(key="A minor"), dict(beat_times=[0.5]), dict(source="jamendo")])
def test_only_unanalyzed_freesound_rows_skip_the_manifest(tmp_path, monkeypatch, over):
    monkeypatch.setattr(report.analysis, "_vocab", lambda: {"instrument": ["piano"]})
    result, _ = report.build_report(dict(tracks=[api_track(**over)], windows=[], stems=[], jobs=[]), tmp_path)
    assert result["api_materialized_audit"] == [] and result["track_audit"][0]["issues"]  # manifest still required


def test_an_ingest_folder_means_a_library_track(tmp_path, monkeypatch):
    monkeypatch.setattr(report.analysis, "_vocab", lambda: {"instrument": ["piano"]})
    (tmp_path / "tracks" / "fs_754932").mkdir(parents=True)
    result, _ = report.build_report(dict(tracks=[api_track()], windows=[], stems=[], jobs=[]), tmp_path)
    assert result["api_materialized_audit"] == [] and result["track_audit"][0]["issues"]


def test_bad_log_line_is_visible_and_secrets_are_not_copied(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"event":"failure","id":"fs_1","password":"private"}\n{"incomplete":')
    events = report.log_events(path)
    assert events == [{"event": "failure", "id": "fs_1"}, {"event": "unreadable_log_line", "line": 2}]


def test_human_review_requires_identified_verified_audio_and_does_not_invent_prominence():
    result = {"track_audit": [dict(id="jam_1", mix_verified=True, hero_cache_verified=True, issues=[])]}
    review = dict(
        track_id="jam_1",
        stem="other",
        audio_path="tracks/jam_1/stems/other.mp3",
        status="identified_track_level_human_review",
        reviewer="human",
        recorded_at="2026-11-14",
        reported_density="denser side",
    )
    report.finish_report(result, [dict(track_id="jam_1", verified=True)], [review, review])
    assert result["acceptance"]["human_reviewed_hero_tracks"] == 1
    assert result["acceptance"]["audibly_verified_prominent_timbres"] == 0
    assert result["acceptance"]["prominent_timbres_30"] == "unverified"
    review["audio_path"] = "tracks/wrong/stems/other.mp3"
    report.finish_report(result, [dict(track_id="jam_1", verified=True)], [review])
    assert result["acceptance"]["human_reviewed_hero_tracks"] == 0
    assert result["listening_reviews"][0]["reported_density"] == "denser side"
