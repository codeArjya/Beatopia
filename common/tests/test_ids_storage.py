from pathlib import Path
from unittest.mock import MagicMock

import pytest

from common import storage
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


@pytest.mark.parametrize("start", [float("nan"), float("inf"), -float("inf")])
def test_window_id_rejects_nonfinite_time(start: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        window_id("fs_1", "mix", start)


def test_upload_uses_bytes_content_type_and_upsert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    client = MagicMock()
    client.storage.__enter__.return_value = client.storage
    monkeypatch.setattr(storage, "create_client", MagicMock(return_value=client))
    local = tmp_path / "mix.mp3"
    local.write_bytes(b"test audio")
    bucket = client.storage.from_.return_value
    received = []
    bucket.upload.side_effect = lambda **kwargs: received.append(kwargs["file"].read())
    for _ in range(2):
        assert storage.upload(str(local), "tracks/fs_1/mix.mp3", "audio/mpeg") == public_url("tracks/fs_1/mix.mp3")
    assert received == [b"test audio", b"test audio"]
    assert bucket.upload.call_args.kwargs["file_options"] == {"content-type": "audio/mpeg", "upsert": "true"}
    assert bucket.upload.call_args.kwargs["file"].closed


def test_upload_requires_service_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY"):
        storage.upload("unused.mp3", "tracks/fs_1/mix.mp3", "audio/mpeg")


def test_public_url_escapes_object_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co/")
    assert public_url("/tracks/a b/mix#1.mp3").endswith("/audio/tracks/a%20b/mix%231.mp3")
