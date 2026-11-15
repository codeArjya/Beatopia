"""T4.2: Gemini rerank + notes (P2) with a mocked client: id hygiene, note rules, skip rules, notes cache write."""

import json
from collections.abc import Iterator
from typing import Any

import jsonschema
import pytest

from app.core import rerank
from app.core.gemini import Gemini
from app.core.scoring import Scored
from app.core.search_sql import Candidate
from tests.test_planner import FakeClient, api_error


def scored(wid: str, score: float, why: str | None = None) -> Scored:
    tid = wid.split(":")[0]
    track = {"id": tid, "title": f"Title {tid}", "key": "A minor", "bpm": 92.4, "beat_times": []}
    c = Candidate(wid, tid, "mix", 0.0, 10.0, ("soul", "rhodes", "a", "b", "c", "d", "e"), 0.5, 0.5, 0.4, why, track)
    return Scored(c, score)


RANKED = [scored(f"jam_{i}:mix:0", 0.9 - i / 100) for i in range(25)]
IDS = [s.candidate.window_id for s in RANKED]


class NotesPool:
    """`write_notes` is monkeypatched to record into this."""

    def __init__(self) -> None:
        self.writes: list[tuple[dict[str, str], str]] = []


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> Iterator[NotesPool]:
    rerank.order_memo.clear()
    p = NotesPool()
    monkeypatch.setattr(rerank, "write_notes", lambda pool, notes, model: pool.writes.append((dict(notes), model)))
    yield p
    rerank.order_memo.clear()


def run(ranked: list[Scored], reply: Any, pool: NotesPool, limit: int = 8) -> tuple[rerank.RerankOutcome, FakeClient]:
    client = FakeClient(reply)
    out = rerank.rerank("dusty soul keys", [], ranked, limit, gemini=Gemini(client, "gm"), pool=pool)  # type: ignore[arg-type]
    return out, client


def ids(out: rerank.RerankOutcome) -> list[str]:
    return [s.candidate.window_id for s in out.ordered]


def test_hallucinated_ids_dropped_and_missing_appended(pool: NotesPool) -> None:
    reply = {"order": [IDS[5], "fs_999:mix:0", IDS[5], IDS[2], 7, IDS[22]], "notes": []}
    out, _ = run(RANKED, reply, pool)
    # fake / duplicate / non-string ids dropped; jam_22 is outside the top 20 so it's not a candidate either;
    # the rest is filled in score order.
    assert ids(out) == [IDS[5], IDS[2], IDS[0], IDS[1], IDS[3], IDS[4], IDS[6], IDS[7]]
    assert out.status == "ok"


def test_notes_only_for_ordered_uncached_ids_and_trimmed(pool: NotesPool) -> None:
    ranked = [scored(IDS[0], 0.9, why="cached one"), *RANKED[1:]]
    long_note = "Warm Rhodes chords with room to breathe. " + "Loop two bars and pitch it down " * 6
    reply = {
        "order": IDS[:8],
        "notes": [
            {"id": IDS[0], "note": "should not replace the cached note"},
            {"id": IDS[1], "note": long_note},
            {"id": IDS[2], "note": "  Short   and sweet.  "},
            {"id": IDS[15], "note": "not in the final order"},
            {"id": "jam_x:mix:0", "note": "hallucinated"},
            {"id": IDS[3], "note": ""},
        ],
    }
    out, client = run(ranked, reply, pool)
    assert out.notes[IDS[0]] == "cached one"
    assert out.notes[IDS[1]] == "Warm Rhodes chords with room to breathe."
    assert out.notes[IDS[2]] == "Short and sweet."
    assert IDS[3] not in out.notes and IDS[15] not in out.notes
    assert out.new_notes == {IDS[1]: out.notes[IDS[1]], IDS[2]: "Short and sweet."}
    assert pool.writes == [(out.new_notes, "gm:meta")]

    content = client.models.calls[0]["contents"]
    needs = json.loads(content.split("needs_note: ")[1])
    assert IDS[0] not in needs and len(needs) == 19  # top 20 minus the cached one
    cands = json.loads(content.split("Candidates:\n")[1].split("\nneeds_note")[0])
    assert len(cands) == rerank.TOP_N
    assert cands[0] == {
        "id": IDS[0],
        "title": "Title jam_0",
        "tags": ["soul", "rhodes", "a", "b", "c", "d"],
        "bpm": 92,
        "key": "A minor",
        "stem": "mix",
        "score": 0.9,
    }
    cfg = client.models.calls[0]["config"]
    assert cfg.response_json_schema == rerank.RERANK_SCHEMA and "the 8 best candidates" in cfg.system_instruction


def test_skip_when_top_limit_all_cached(pool: NotesPool) -> None:
    ranked = [scored(w, 0.9 - i / 100, why=f"note {i}" if i < 3 else None) for i, w in enumerate(IDS)]
    out, client = run(ranked, {"order": [], "notes": []}, pool, limit=3)
    assert out.status == "skipped:cached" and client.models.calls == []
    assert ids(out) == IDS[:3] and out.notes == {IDS[0]: "note 0", IDS[1]: "note 1", IDS[2]: "note 2"}


@pytest.mark.parametrize("reply", [api_error(503), "garbage", TimeoutError()])
def test_failure_keeps_score_order_and_cached_notes(pool: NotesPool, reply: Any) -> None:
    ranked = [scored(IDS[0], 0.9, why="cached"), *RANKED[1:]]
    out, _ = run(ranked, reply, pool)
    assert out.status == "failed" and ids(out) == IDS[:8] and out.notes == {IDS[0]: "cached"}
    assert pool.writes == []


def test_no_client_degraded_and_few(pool: NotesPool) -> None:
    assert rerank.rerank("x", [], RANKED, 8, gemini=None, pool=pool).status == "skipped:no_client"  # type: ignore[arg-type]
    off = Gemini(None, "gm", disabled_reason="GEMINI_DEGRADED=1")
    assert rerank.rerank("x", [], RANKED, 8, gemini=off, pool=pool).status == "skipped:degraded"  # type: ignore[arg-type]
    out, client = run(RANKED[:1], {"order": [], "notes": []}, pool)
    assert out.status == "skipped:few" and client.models.calls == []
    assert rerank.rerank("x", [], [], 8, gemini=None, pool=pool).ordered == []  # type: ignore[arg-type]


def test_repeat_search_reuses_the_memo_and_skips_gemini(pool: NotesPool) -> None:
    order = [IDS[9], IDS[3], IDS[12], IDS[0], IDS[1], IDS[2], IDS[4], IDS[5]]
    reply = {"order": order, "notes": [{"id": i, "note": f"note {i}."} for i in order]}
    first, _ = run(RANKED, reply, pool)
    assert first.status == "ok" and ids(first) == order

    # Run 2: the SQL join now returns those notes; the score-order top 8 is a different set, so only the memo helps.
    noted = [scored(s.candidate.window_id, s.score, why=first.notes.get(s.candidate.window_id)) for s in RANKED]
    second, client = run(noted, reply, pool)
    assert second.status == "skipped:memo" and client.models.calls == []
    assert ids(second) == order and len(second.notes) == rerank.NOTES_PER_RERANK  # the top 4; /why fills the rest

    # A different request (or candidate set) doesn't reuse it.
    other = rerank.rerank("other words", [], noted, 8, gemini=None, pool=pool)  # type: ignore[arg-type]
    assert other.status == "skipped:no_client" and ids(other) == IDS[:8]


def test_memo_order_survives_a_gemini_outage(pool: NotesPool) -> None:
    order = [IDS[9], IDS[3]]
    run(RANKED, {"order": order, "notes": []}, pool, limit=2)
    out, _ = run(RANKED, api_error(503), pool, limit=2)  # no notes cached → Gemini is tried, fails
    assert out.status == "failed" and ids(out) == order


def test_notes_write_error_is_not_fatal(pool: NotesPool, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: Any) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(rerank, "write_notes", broken)
    out, _ = run(RANKED, {"order": IDS[:8], "notes": [{"id": IDS[0], "note": "Nice."}]}, pool)
    assert out.status == "ok" and out.notes == {IDS[0]: "Nice."}


def test_schema_and_trim_note() -> None:
    jsonschema.Draft202012Validator.check_schema(rerank.RERANK_SCHEMA)
    assert rerank.trim_note("one two three", 5) == "one two three"
    assert rerank.trim_note("One two. Three four five six", 5) == "One two."
    assert rerank.trim_note("one two three, four five six", 4) == "one two three, four…"
    assert rerank.trim_note("Ends right here. More words", 3) == "Ends right here."


def test_new_notes_are_capped_to_the_top_of_the_order(pool: NotesPool) -> None:
    order = [IDS[9], IDS[3], IDS[12], IDS[0], IDS[1], IDS[2], IDS[4], IDS[5]]
    reply = {"order": order, "notes": [{"id": i, "note": f"note {i}."} for i in reversed(order)]}
    out, client = run(RANKED, reply, pool)
    assert set(out.new_notes) == set(order[: rerank.NOTES_PER_RERANK])
    assert f"first {rerank.NOTES_PER_RERANK} ids" in client.models.calls[0]["config"].system_instruction
