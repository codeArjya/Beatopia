"""T4.2 / T11.1: Gemini rerank (P2a order, aliases) + background notes (P2b) with a mocked client: id hygiene,
note rules, skip rules, notes cache write, the notes deadline and the pending-note registry."""

import json
import threading
import time
from collections.abc import Iterator
from typing import Any

import jsonschema
import pytest

from app.core import rerank
from app.core.gemini import Gemini
from app.core.scoring import Scored
from app.core.search_sql import Candidate
from tests.test_planner import FakeResponse, api_error


def scored(wid: str, score: float, why: str | None = None) -> Scored:
    tid = wid.split(":")[0]
    track = {"id": tid, "title": f"Title {tid}", "key": "A minor", "bpm": 92.4, "beat_times": []}
    c = Candidate(wid, tid, "mix", 0.0, 10.0, ("soul", "rhodes", "a", "b", "c", "d", "e"), 0.5, 0.5, 0.4, why, track)
    return Scored(c, score)


RANKED = [scored(f"jam_{i}:mix:0", 0.9 - i / 100) for i in range(25)]
IDS = [s.candidate.window_id for s in RANKED]


def alias(*idx: int) -> list[str]:
    """Positions in RANKED (0-based) → P2a aliases ("1"-based)."""
    return [str(i + 1) for i in idx]


class SplitModels:
    """Answers the order call (P2a) and the notes call (P2b) separately, by response schema."""

    def __init__(self, order: Any, notes: Any = None, *, notes_gate: threading.Event | None = None) -> None:
        self.order, self.notes, self.notes_gate = order, notes, notes_gate
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def generate_content(self, *, model: str, contents: Any, config: Any) -> FakeResponse:
        kind = "order" if "order" in config.response_json_schema["properties"] else "notes"
        with self._lock:
            self.calls.append({"kind": kind, "contents": contents, "config": config})
        if kind == "notes" and self.notes_gate is not None:
            self.notes_gate.wait(5)
        reply = self.order if kind == "order" else self.notes
        if callable(reply) and not isinstance(reply, Exception):
            reply = reply(contents)
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(reply if isinstance(reply, str) else json.dumps(reply))

    def kinds(self) -> list[str]:
        return [c["kind"] for c in self.calls]


class SplitClient:
    def __init__(self, order: Any, notes: Any = None, **kw: Any) -> None:
        self.models = SplitModels(order, notes, **kw)


def notes_for_all(contents: str) -> dict[str, Any]:
    """A P2b reply with one note per window it was asked about ("note <title>.")."""
    windows = json.loads(contents.split("Windows:\n")[1])
    return {"notes": [{"id": w["id"], "note": f"note {w['title']}."} for w in windows]}


class NotesPool:
    """`write_notes` is monkeypatched to record into this."""

    def __init__(self) -> None:
        self.writes: list[tuple[dict[str, str], str]] = []


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> Iterator[NotesPool]:
    rerank.order_memo.clear()
    rerank.pending.clear()
    p = NotesPool()
    monkeypatch.setattr(rerank, "write_notes", lambda pool, notes, model: pool.writes.append((dict(notes), model)))
    yield p
    rerank.order_memo.clear()
    rerank.pending.clear()


def run(ranked: list[Scored], client: SplitClient, pool: NotesPool, limit: int = 8, **kw: Any) -> rerank.RerankOutcome:
    gemini = Gemini(client, "gm")
    return rerank.rerank("dusty soul keys", [], ranked, limit, gemini=gemini, pool=pool, **kw)  # type: ignore[arg-type]


def ids(out: rerank.RerankOutcome) -> list[str]:
    return [s.candidate.window_id for s in out.ordered]


def test_aliases_mapped_hallucinations_dropped_and_missing_appended(pool: NotesPool) -> None:
    # "6" twice, a window id instead of an alias, an alias past the top 20, a bool, an int alias (tolerated).
    order = ["6", "6", IDS[1], "23", True, 3, " 1 "]
    client = SplitClient({"order": order}, notes_for_all)
    out = run(RANKED, client, pool)
    assert ids(out) == [IDS[5], IDS[2], IDS[0], IDS[1], IDS[3], IDS[4], IDS[6], IDS[7]]
    assert out.status == "ok"

    content = client.models.calls[0]["contents"]
    cands = json.loads(content.split("Candidates:\n")[1])
    assert len(cands) == rerank.TOP_N and [c["id"] for c in cands] == [str(i) for i in range(1, 21)]
    assert cands[0] == {
        "id": "1",
        "title": "Title jam_0",
        "tags": ["soul", "rhodes", "a", "b", "c", "d"],
        "bpm": 92,
        "key": "A minor",
        "stem": "mix",
        "score": 0.9,
    }
    cfg = client.models.calls[0]["config"]
    assert cfg.response_json_schema == rerank.ORDER_SCHEMA and "the 8 best candidates" in cfg.system_instruction
    assert "needs_note" not in content and "notes" not in cfg.system_instruction.lower()


def test_notes_for_the_top_uncached_of_the_order_trimmed_and_stored(pool: NotesPool) -> None:
    ranked = [scored(IDS[0], 0.9, why="cached one"), *RANKED[1:]]
    long_note = "Warm Rhodes chords with room to breathe. " + "Loop two bars and pitch it down " * 6
    notes = {
        "notes": [
            {"id": "1", "note": long_note},
            {"id": 2, "note": "  Short   and sweet.  "},
            {"id": "9", "note": "not one of the windows asked about"},
            {"id": "3", "note": ""},
            {"id": "1", "note": "duplicate"},
        ]
    }
    client = SplitClient({"order": alias(*range(8))}, notes)
    out = run(ranked, client, pool)
    assert client.models.kinds() == ["order", "notes"]
    # P2b was asked about the first 4 uncached windows of the order, with fresh aliases and no scores.
    asked = json.loads(client.models.calls[1]["contents"].split("Windows:\n")[1])
    assert [w["title"] for w in asked] == ["Title jam_1", "Title jam_2", "Title jam_3", "Title jam_4"]
    assert [w["id"] for w in asked] == ["1", "2", "3", "4"] and "score" not in asked[0]
    assert client.models.calls[1]["config"].response_json_schema == rerank.NOTES_SCHEMA

    assert out.notes[IDS[0]] == "cached one"
    assert out.notes[IDS[1]] == "Warm Rhodes chords with room to breathe."
    assert out.notes[IDS[2]] == "Short and sweet."
    assert IDS[3] not in out.notes and IDS[4] not in out.notes
    assert out.new_notes == {IDS[1]: out.notes[IDS[1]], IDS[2]: "Short and sweet."} and out.notes_pending == 0
    assert pool.writes == [(out.new_notes, "gm:meta")]


def test_skip_when_top_limit_all_cached(pool: NotesPool) -> None:
    ranked = [scored(w, 0.9 - i / 100, why=f"note {i}" if i < 3 else None) for i, w in enumerate(IDS)]
    client = SplitClient({"order": []})
    out = run(ranked, client, pool, limit=3)
    assert out.status == "skipped:cached" and client.models.calls == []
    assert ids(out) == IDS[:3] and out.notes == {IDS[0]: "note 0", IDS[1]: "note 1", IDS[2]: "note 2"}


@pytest.mark.parametrize("reply", [api_error(503), "garbage", TimeoutError()])
def test_order_failure_keeps_score_order_and_cached_notes(pool: NotesPool, reply: Any) -> None:
    ranked = [scored(IDS[0], 0.9, why="cached"), *RANKED[1:]]
    client = SplitClient(reply, notes_for_all)
    out = run(ranked, client, pool)
    assert out.status == "failed" and ids(out) == IDS[:8] and out.notes == {IDS[0]: "cached"}
    assert pool.writes == [] and client.models.kinds() == ["order"]  # no notes call after a failed order


def test_notes_failure_keeps_the_order(pool: NotesPool) -> None:
    client = SplitClient({"order": alias(3, 2, 1, 0)}, api_error(503))
    out = run(RANKED, client, pool)
    assert out.status == "ok" and ids(out)[:4] == [IDS[3], IDS[2], IDS[1], IDS[0]]
    assert out.notes == {} and out.new_notes == {} and pool.writes == []


def test_no_client_degraded_and_few(pool: NotesPool) -> None:
    assert rerank.rerank("x", [], RANKED, 8, gemini=None, pool=pool).status == "skipped:no_client"  # type: ignore[arg-type]
    off = Gemini(None, "gm", disabled_reason="GEMINI_DEGRADED=1")
    assert rerank.rerank("x", [], RANKED, 8, gemini=off, pool=pool).status == "skipped:degraded"  # type: ignore[arg-type]
    client = SplitClient({"order": []})
    out = run(RANKED[:1], client, pool)
    assert out.status == "skipped:few" and client.models.calls == []
    assert rerank.rerank("x", [], [], 8, gemini=None, pool=pool).ordered == []  # type: ignore[arg-type]


def test_repeat_search_reuses_the_memo_and_skips_gemini(pool: NotesPool) -> None:
    order_idx = [9, 3, 12, 0, 1, 2, 4, 5]
    order = [IDS[i] for i in order_idx]
    first = run(RANKED, SplitClient({"order": alias(*order_idx)}, notes_for_all), pool)
    assert first.status == "ok" and ids(first) == order
    assert set(first.new_notes) == set(order[: rerank.NOTES_PER_RERANK])

    # Run 2: the SQL join now returns those notes; the score-order top 8 is a different set, so only the memo helps.
    noted = [scored(s.candidate.window_id, s.score, why=first.notes.get(s.candidate.window_id)) for s in RANKED]
    client = SplitClient({"order": []}, notes_for_all)
    second = run(noted, client, pool)
    assert second.status == "skipped:memo" and client.models.calls == []
    assert ids(second) == order and len(second.notes) == rerank.NOTES_PER_RERANK  # the top 4; /why fills the rest

    # A different request (or candidate set) doesn't reuse it.
    other = rerank.rerank("other words", [], noted, 8, gemini=None, pool=pool)  # type: ignore[arg-type]
    assert other.status == "skipped:no_client" and ids(other) == IDS[:8]


def test_memo_hit_without_notes_only_writes_notes(pool: NotesPool) -> None:
    run(RANKED, SplitClient({"order": alias(9, 3)}, api_error(503)), pool, limit=2)  # order memoized, notes failed
    client = SplitClient(api_error(503), notes_for_all)
    out = run(RANKED, client, pool, limit=2)
    assert out.status == "skipped:memo" and ids(out) == [IDS[9], IDS[3]]
    assert client.models.kinds() == ["notes"] and set(out.notes) == {IDS[9], IDS[3]}


def test_notes_write_error_is_not_fatal(pool: NotesPool, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: Any) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(rerank, "write_notes", broken)
    out = run(RANKED, SplitClient({"order": alias(*range(8))}, {"notes": [{"id": "1", "note": "Nice."}]}), pool)
    assert out.status == "ok" and out.notes == {IDS[0]: "Nice."}


def test_late_notes_answer_without_them_and_are_pending_for_why(pool: NotesPool) -> None:
    gate = threading.Event()
    client = SplitClient({"order": alias(*range(8))}, notes_for_all, notes_gate=gate)
    t = time.monotonic()
    out = run(RANKED, client, pool, notes_until=time.monotonic() + 0.05)
    assert time.monotonic() - t < 2.0  # didn't wait for the gated notes call
    assert out.status == "ok" and out.notes == {} and out.new_notes == {}
    assert out.notes_pending == rerank.NOTES_PER_RERANK and pool.writes == []

    # A concurrent search over the same windows doesn't start a second notes call, it waits on the first one.
    assert rerank.pending.wait(IDS[7], 0.01) is None  # IDS[7] isn't among the top 4 being written
    gate.set()
    assert rerank.pending.wait(IDS[0], 5) == "note Title jam_0."  # what POST /why does
    deadline = time.monotonic() + 5
    while rerank.pending.futures([IDS[0]]) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert rerank.pending.futures(IDS) == {}  # released once written
    assert pool.writes == [({IDS[i]: f"note Title jam_{i}." for i in range(4)}, "gm:meta")]
    assert client.models.kinds() == ["order", "notes"]


def test_concurrent_searches_share_pending_notes(pool: NotesPool) -> None:
    gate = threading.Event()
    first = SplitClient({"order": alias(*range(8))}, notes_for_all, notes_gate=gate)
    run(RANKED, first, pool, notes_until=time.monotonic())
    second = SplitClient({"order": alias(*range(8))}, notes_for_all)
    rerank.order_memo.clear()  # a different request would have its own memo entry; force a fresh order call
    threading.Timer(0.1, gate.set).start()
    out = run(RANKED, second, pool)
    assert second.models.kinds() == ["order"]  # no second notes call: it waited for the first one's
    assert set(out.notes) == set(IDS[:4])


def test_schemas_and_trim_note() -> None:
    jsonschema.Draft202012Validator.check_schema(rerank.ORDER_SCHEMA)
    jsonschema.Draft202012Validator.check_schema(rerank.NOTES_SCHEMA)
    assert rerank.trim_note("one two three", 5) == "one two three"
    assert rerank.trim_note("One two. Three four five six", 5) == "One two."
    assert rerank.trim_note("one two three, four five six", 4) == "one two three, four…"
    assert rerank.trim_note("Ends right here. More words", 3) == "Ends right here."


def test_new_notes_are_capped_to_the_top_of_the_order(pool: NotesPool) -> None:
    order_idx = [9, 3, 12, 0, 1, 2, 4, 5]
    client = SplitClient({"order": alias(*order_idx)}, notes_for_all)
    out = run(RANKED, client, pool)
    assert set(out.new_notes) == {IDS[i] for i in order_idx[: rerank.NOTES_PER_RERANK]}
    asked = json.loads(client.models.calls[1]["contents"].split("Windows:\n")[1])
    assert len(asked) == rerank.NOTES_PER_RERANK
