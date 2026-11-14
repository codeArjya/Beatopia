import common.ids
import ingest.run


def test_imports() -> None:
    assert callable(ingest.run.main)
    assert common.ids.window_id("fs_1", "mix", 5) == "fs_1:mix:5000"
