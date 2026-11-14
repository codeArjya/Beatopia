import pytest

from common.ids import window_id
from common.storage import public_url


def test_window_id_contract_example() -> None:
    assert window_id("fs_482913", "mix", 15.0) == "fs_482913:mix:15000"


def test_window_id_rounds_to_ms() -> None:
    assert window_id("jam_1532881", "drums", 10.6666667) == "jam_1532881:drums:10667"
    assert window_id("imp_3f9a1c2e", "mix", 0) == "imp_3f9a1c2e:mix:0"


def test_window_id_rejects_negative() -> None:
    with pytest.raises(ValueError):
        window_id("fs_1", "mix", -1)


def test_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co/")
    assert (
        public_url("tracks/fs_482913/mix.mp3")
        == "https://abc.supabase.co/storage/v1/object/public/audio/tracks/fs_482913/mix.mp3"
    )


def test_public_url_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        public_url("tracks/x/mix.mp3")
