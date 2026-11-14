"""T2.1: /chips built from ingest/vocab.txt + tempo/key chips."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.core.chips import build_chips, chip_index, label, load_chips, parse_vocab, slug
from app.core.settings import Settings
from app.fixture_routes import fixture
from app.models.api import ChipsResponse

VOCAB = Settings.from_env({}).vocab_path


def test_generated_chips_equal_the_fixture() -> None:
    # The fixture is the contract example WS3 builds against: the live response must be identical.
    assert load_chips(VOCAB) == ChipsResponse.model_validate(fixture("chips"))


def test_slugs_and_labels() -> None:
    assert slug("synth pad") == "synth_pad"
    assert slug("hi-hats") == "hi_hats"
    assert slug("r&b") == "rnb"
    assert slug("C# minor") == "c_sharp_minor"
    assert slug("808") == "808"
    assert label("r&b") == "R&B"
    assert label("lo-fi") == "Lo-fi"


def test_chip_index_has_the_fixture_ids() -> None:
    index = chip_index(VOCAB)
    assert index["inst.trumpet"].filter.tags == ["trumpet"]
    assert index["genre.soul"].category == "genre"
    assert index["tempo.90"].filter.bpm_range == (85, 95)
    assert index["key.a_minor"].filter.key == "A minor"
    assert len(index) == 60 + 30 + 30 + 10 + 24


def test_parse_vocab_rejects_bad_files(tmp_path: Path) -> None:
    orphan = tmp_path / "orphan.txt"
    orphan.write_text("trumpet\n# instrument\n", encoding="utf-8")
    with pytest.raises(ValueError, match="before any category"):
        parse_vocab(orphan)

    partial = tmp_path / "partial.txt"
    partial.write_text("# instrument\ntrumpet\n# genre\nsoul\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mood"):
        parse_vocab(partial)


def test_duplicate_slugs_are_rejected() -> None:
    with pytest.raises(ValueError, match="inst.hi_hats"):
        build_chips({"instrument": ["hi-hats", "hi hats"], "genre": [], "mood": []})


def test_real_chips_route() -> None:
    real = Settings.from_env({"SUPABASE_URL": "https://ref.supabase.co"})
    body = TestClient(main.create_app(real)).get("/chips")
    assert body.status_code == 200
    assert ChipsResponse.model_validate(body.json()) == load_chips(VOCAB)
