import common.ids
import worker.main


def test_imports() -> None:
    assert callable(worker.main.main)
    assert common.ids.window_id("fs_1", "mix", 5) == "fs_1:mix:5000"
