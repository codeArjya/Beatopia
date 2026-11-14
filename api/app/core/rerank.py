"""Gemini rerank + notes (CONTRACT §7.6, prompt P2): one call per search over the top 20 scored windows.

Gemini returns the ids of the best `limit` windows in order, plus a ≤ 30-word note for each of them that has no
cached note yet. Ids that aren't candidates are dropped; missing ones are appended in score order. New notes are
written to `notes` with model "<model>:meta".

Gemini's order is memoized in process per (request, chips, limit, top-20 ids). Without a fresh rerank, results use
that memo, else the score order, with cached notes only. The rerank is skipped when every one of those results
already has a cached note ("skipped:memo" / "skipped:cached"), when there is no client or Gemini is degraded, and on
any failure or timeout ("failed").
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field

from psycopg_pool import ConnectionPool

from app.core.gemini import CallBudget, Gemini, GeminiUnavailable
from app.core.scoring import Scored
from app.models.api import Chip

log = logging.getLogger("app.rerank")

TOP_N = 20
RERANK_BUDGET = CallBudget(timeout_ms=4_000, attempts=1)
RERANK_TEMPERATURE = 0.2
NOTE_MAX_WORDS = 30
CANDIDATE_TAGS = 6
MAX_IDS = 24  # SearchRequest.limit ≤ 24
ORDER_MEMO_SIZE = 1024

SYSTEM_TEMPLATE = """\
You help a beginner music producer pick samples. You get their search request and a list of candidate
windows from a Creative Commons library (already roughly ranked by an audio search model; "score" is
that model's confidence). Each candidate has an id, the track title, auto-detected tags, tempo, key,
which stem it is (mix = full song, or an isolated part) and the score.

1. Return "order": the ids of the {limit} best candidates for this request, best first. Use only ids from
   the list. Favor candidates whose tags clearly match what was asked, prefer isolated stems or sparse
   moments when the user asked for something clean, and avoid putting several windows of the same
   track next to each other. Trust the score when the metadata gives no reason to disagree.
2. Return "notes": for each id in "order" that is listed under needs_note, one note of at most 30 words,
   in plain friendly English for someone new to sampling: why this window could work as a sample for
   this request, and one concrete thing to try (chop on the chord changes, loop 2 bars, pitch it down,
   filter out the low end, and so on). Base it only on the metadata; do not claim things you cannot
   know from it, and do not mention scores or ids.
"""

RERANK_SCHEMA = {
    "type": "object",
    "properties": {
        "order": {"type": "array", "maxItems": MAX_IDS, "items": {"type": "string"}},
        "notes": {
            "type": "array",
            "maxItems": MAX_IDS,
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "note": {"type": "string"}},
                "required": ["id", "note"],
            },
        },
    },
    "required": ["order", "notes"],
}


@dataclass
class RerankOutcome:
    ordered: list[Scored]  # the final `limit` results, best first
    notes: dict[str, str]  # window id → note (cached or new) for the ordered windows
    status: str  # "ok" | "skipped:<why>" | "failed"
    new_notes: dict[str, str] = field(default_factory=dict)


def trim_note(text: str, max_words: int = NOTE_MAX_WORDS) -> str:
    """Collapse whitespace; over `max_words`, cut at the last sentence end inside the limit (else hard cut + '…')."""
    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)
    head = " ".join(words[:max_words])
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", head)]
    return head[: ends[-1]] if ends else head.rstrip(",;:") + "…"


def candidate_json(s: Scored) -> dict[str, object]:
    c = s.candidate
    return {
        "id": c.window_id,
        "title": c.track["title"],
        "tags": list(c.tags[:CANDIDATE_TAGS]),
        "bpm": round(c.bpm) if c.bpm is not None else None,
        "key": c.track["key"],
        "stem": c.stem,
        "score": round(s.score, 2),
    }


def user_content(request: str, chips: Sequence[Chip], top: Sequence[Scored], needs_note: Sequence[str]) -> str:
    labels = ", ".join(c.label for c in chips) or "none"
    cands = json.dumps([candidate_json(s) for s in top], ensure_ascii=False, separators=(",", ":"))
    return (
        f"Request: {json.dumps(request, ensure_ascii=False)}\nSelected chips: {labels}\n"
        f"Candidates:\n{cands}\nneeds_note: {json.dumps(list(needs_note))}"
    )


def apply_order(top: Sequence[Scored], order: object, limit: int) -> list[Scored]:
    """Gemini's order, keeping only real, unseen candidate ids; then the rest in score order; cut to `limit`."""
    by_id = {s.candidate.window_id: s for s in top}
    picked: list[Scored] = []
    seen: set[str] = set()
    for wid in order if isinstance(order, list) else []:
        if isinstance(wid, str) and wid in by_id and wid not in seen:
            seen.add(wid)
            picked.append(by_id[wid])
    picked += [s for s in top if s.candidate.window_id not in seen]
    return picked[:limit]


def parse_notes(raw: object, wanted: set[str]) -> dict[str, str]:
    notes: dict[str, str] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        wid, text = item.get("id"), item.get("note")
        if isinstance(wid, str) and wid in wanted and isinstance(text, str) and text.strip() and wid not in notes:
            notes[wid] = trim_note(text)
    return notes


def write_notes(pool: ConnectionPool, notes: dict[str, str], model: str) -> None:
    """Insert new notes; an existing note for the window wins (first writer, e.g. a concurrent /why)."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.executemany(
            "insert into notes (window_id, text, model) values (%s, %s, %s) on conflict (window_id) do nothing",
            [(wid, text, model) for wid, text in notes.items()],
        )


class _OrderMemo:
    """In-process LRU: rerank key → Gemini's ordered ids. Repeat searches reuse it, so they skip Gemini entirely
    once the notes are cached (the score-order top `limit` usually differs from the reranked set)."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._data: OrderedDict[str, list[str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> list[str] | None:
        with self._lock:
            ids = self._data.get(key)
            if ids is not None:
                self._data.move_to_end(key)
            return ids

    def put(self, key: str, ids: list[str]) -> None:
        with self._lock:
            self._data[key] = ids
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


order_memo = _OrderMemo(ORDER_MEMO_SIZE)


def order_key(request: str, chips: Sequence[Chip], limit: int, top: Sequence[Scored]) -> str:
    parts = [
        " ".join(request.lower().split()),
        sorted(c.id for c in chips),
        limit,
        [s.candidate.window_id for s in top],
    ]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _cached(scored: Sequence[Scored]) -> dict[str, str]:
    return {s.candidate.window_id: s.candidate.why for s in scored if s.candidate.why}


def rerank(
    request: str,
    chips: Sequence[Chip],
    ranked: Sequence[Scored],
    limit: int,
    *,
    gemini: Gemini | None,
    pool: ConnectionPool,
) -> RerankOutcome:
    top = list(ranked[:TOP_N])
    cached = _cached(top)
    key = order_key(request, chips, limit, top)
    memo = order_memo.get(key)
    # Without a fresh rerank, use the order Gemini gave last time for exactly this request and candidate set,
    # else the score order.
    fallback_order = apply_order(top, memo, limit) if memo is not None else top[:limit]

    def keep(status: str) -> RerankOutcome:
        return RerankOutcome(fallback_order, _cached(fallback_order), status)

    if len(top) <= 1:
        return keep("skipped:few")
    if all(s.candidate.window_id in cached for s in fallback_order):
        return keep("skipped:memo" if memo is not None else "skipped:cached")
    if gemini is None:
        return keep("skipped:no_client")
    if not gemini.available():
        return keep("skipped:degraded")

    needs_note = [s.candidate.window_id for s in top if s.candidate.window_id not in cached]
    try:
        raw = gemini.generate_json(
            system=SYSTEM_TEMPLATE.format(limit=min(limit, len(top))),
            contents=user_content(request, chips, top, needs_note),
            schema=RERANK_SCHEMA,
            temperature=RERANK_TEMPERATURE,
            budget=RERANK_BUDGET,
            what="rerank",
        )
    except GeminiUnavailable:
        return keep("failed")

    ordered = apply_order(top, raw.get("order"), limit)
    order_memo.put(key, [s.candidate.window_id for s in ordered])
    ordered_ids = {s.candidate.window_id for s in ordered}
    new = parse_notes(raw.get("notes"), ordered_ids & set(needs_note))
    if new:
        try:
            write_notes(pool, new, f"{gemini.model}:meta")
        except Exception:
            log.warning("notes write failed", exc_info=True)
    notes = {wid: cached.get(wid) or new.get(wid) for wid in ordered_ids}
    return RerankOutcome(ordered, {k: v for k, v in notes.items() if v}, "ok", new)
