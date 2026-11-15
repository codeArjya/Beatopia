import json
from pathlib import Path

import numpy as np
import pytest

from ingest import calibrate

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_mapping_matches_existing_fixture_and_vocab():
    actual = calibrate.mapping_snapshot(ROOT / "shared/fixtures/chips.json")
    frozen = json.loads((ROOT / "ingest/vocab-freeze.json").read_text())
    for key in ("tags", "categories", "vocab_sha256", "fixture_sha256", "prompt", "selection"):
        assert actual[key] == frozen[key]
    assert actual["categories"] == {"instrument": 60, "genre": 30, "mood": 30}
    assert actual["tags"]["saxophone"]["id"] == "inst.saxophone"
    assert actual["tags"]["bass guitar"]["id"] == "inst.bass_guitar"


def test_runtime_freeze_rejects_model_or_mapping_drift(tmp_path, monkeypatch):
    frozen_path = ROOT / "ingest/vocab-freeze.json"
    frozen = json.loads(frozen_path.read_text())
    identity = {**calibrate.pipeline.fingerprint(), "model": frozen["model"], "revision": frozen["revision"]}
    monkeypatch.setattr(calibrate.pipeline, "fingerprint", lambda: identity)
    assert calibrate.frozen_mapping(ROOT / "shared/fixtures/chips.json", frozen_path) == frozen
    frozen["tags"]["piano"]["id"] = "inst.renamed"
    changed = tmp_path / "freeze.json"
    changed.write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="Frozen"):
        calibrate.frozen_mapping(ROOT / "shared/fixtures/chips.json", changed)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "wrong_category", "unknown"])
def test_freeze_rejects_chip_mapping_drift(tmp_path, damage):
    fixture = json.loads((ROOT / "shared/fixtures/chips.json").read_text())
    chips = fixture["categories"][0]["chips"]
    if damage == "missing":
        chips.pop()
    elif damage == "duplicate":
        chips[1]["id"] = chips[0]["id"]
    elif damage == "wrong_category":
        chips[0]["category"] = "mood"
    else:
        chips[0]["filter"]["tags"] = ["invented"]
    path = tmp_path / "chips.json"
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValueError, match="mapping"):
        calibrate.mapping_snapshot(path)


def test_replay_reports_changes_without_mutating_cached_metadata(monkeypatch):
    windows = [dict(id="fs_1:mix:0", tags=["piano"], tag_scores={"piano": 0.3})]
    monkeypatch.setattr(calibrate.analysis, "zero_shot_tags", lambda vectors: [(["piano"], {"piano": 0.3})])
    result = calibrate.replay(windows, np.ones((1, 512)))
    assert result["changes"] == []
    monkeypatch.setattr(calibrate.analysis, "zero_shot_tags", lambda vectors: [([], {"piano": 0.1})])
    result = calibrate.replay(windows, np.ones((1, 512)))
    assert len(result["changes"]) == 1
    assert result["changes"][0]["max_score_delta"] == pytest.approx(0.2)
    assert windows[0]["tags"] == ["piano"]
    assert windows[0]["tag_scores"] == {"piano": 0.3}


def test_examples_deduplicate_tracks_and_include_random_stem_windows():
    rows = [
        dict(
            id=f"fs_{i}:mix:{j}",
            track_id=f"fs_{i}",
            stem="mix",
            density=i / 10,
            tags=["piano"],
            tag_scores={"piano": 0.3},
        )
        for i in range(10)
        for j in range(3)
    ]
    rows.append(
        dict(id="fs_1:vocals:0", track_id="fs_1", stem="vocals", density=0.4, tags=[], tag_scores={"piano": 0.1})
    )
    assert len({w["track_id"] for w in calibrate.distinct_examples(rows, 4)}) == 4
    examples = calibrate.audition_rows(rows, {"fs_1", "fs_2"}, {"fs_1:vocals:0"})
    assert len(examples) == len({w["id"] for w in examples})
    assert any(w["id"] == "fs_1:vocals:0" for w in examples)
    assert sum(any("hero prominent" in r for r in w["selection_reasons"]) for w in examples) == 2


def test_audition_escapes_source_metadata_and_bounds_playback(tmp_path):
    path = tmp_path / "audition.html"
    calibrate.write_audition(
        path,
        [
            dict(
                id="fs_1:mix:0",
                title="<script>bad</script>",
                artist="A & B",
                selection_reasons=["density"],
                tags=["piano"],
                density=0.1,
                start_s=5,
                end_s=15,
                audio_url="https://example.test/mix.mp3",
                attribution="Credit <name>",
                license="CC0",
            )
        ],
    )
    page = path.read_text(encoding="utf-8")
    assert "<script>bad</script>" not in page
    assert "&lt;script&gt;bad&lt;/script&gt;" in page
    assert 'data-start="5" data-end="15"' in page
    assert "Listening: unreviewed" in page
    assert "timeupdate" in page
