"""Gemini rerank + notes (CONTRACT §7.6, prompts P2a / P2b) over the top 20 scored windows.

Two calls, so that only the fast one is on the search's critical path (T11.1, measured on gemini-3.6-flash: order
+ 4 notes in one call ≈ 2.4–3.3 s, order alone ≈ 0.9–1.2 s):

- **P2a order** (blocking): the ids of the best `limit` windows, best first. Candidates are sent with short numeric
  aliases ("1".."20") instead of window ids, which are long and cost output tokens. Aliases that aren't candidates
  are dropped; missing candidates are appended in score order.
- **P2b notes** (background): a ≤ 30-word note for each of the first `NOTES_PER_RERANK` windows of that order with no
  cached note, written to `notes` as "<model>:meta". The search waits for them only until `notes_until` (a monotonic
  deadline set by the caller); notes that land later are in the cache for `POST /why` (which waits on a pending
  note instead of generating its own, see `pending`) and for repeat searches.

Gemini's order is memoized in process per (request, chips, limit, top-20 ids). A memo hit skips P2a; P2b still runs
for top windows without notes. Everything is skipped when every result already has a cached note
("skipped:memo" / "skipped:cached"), with no client or Gemini degraded, and P2a failing or timing out ("failed")
leaves the memo or score order with cached notes only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from concurrent.futures import wait as wait_futures
from dataclasses import dataclass, field

from psycopg_pool import ConnectionPool

from app.core.gemini import CallBudget, Gemini, GeminiUnavailable
from app.core.scoring import Scored
from app.models.api import Chip

log = logging.getLogger("app.rerank")

TOP_N = 20
ORDER_BUDGET = CallBudget(timeout_ms=3_000, attempts=1)
NOTES_BUDGET = CallBudget(timeout_ms=10_000, attempts=2)  # background: not on the search's critical path
RERANK_TEMPERATURE = 0.2
NOTE_MAX_WORDS = 30
# New notes per search: the top results get notes, the rest stay `why: null` for POST /why (CONTRACT §5).
NOTES_PER_RERANK = 4
CANDIDATE_TAGS = 6
MAX_IDS = 24  # SearchRequest.limit ≤ 24
ORDER_MEMO_SIZE = 1024
NOTES_WORKERS = 4

ORDER_SYSTEM_TEMPLATE = """\
You help a beginner music producer pick samples. You get their search request and a list of candidate
windows from a Creative Commons library (already roughly ranked by an audio search model; "score" is
that model's confidence). Each candidate has a number ("id"), the track title, auto-detected tags, tempo,
key, which stem it is (mix = full song, or an isolated part) and the score.

Return "order": the ids of the {limit} best candidates for this request, best first. Use only ids from
the list. Favor candidates whose tags clearly match what was asked, prefer isolated stems or sparse
moments when the user asked for something clean, and avoid putting several windows of the same
track next to each other. Trust the score when the metadata gives no reason to disagree.
"""

NOTES_SYSTEM = """\
You help a beginner music producer pick samples. You get their search request and a few windows from a
Creative Commons library that were picked for it. Each window has a number ("id"), the track title,
auto-detected tags, tempo, key and which stem it is (mix = full song, or an isolated part).

Return "notes": one note for every window, at most 30 words each, in plain friendly English for someone
new to sampling: why this window could work as a sample for this request, and one concrete thing to try
(chop on the chord changes, loop 2 bars, pitch it down, filter out the low end, and so on). Base it only
on the metadata; do not claim things you cannot know from it, and do not mention ids or numbers of windows.
"""

ORDER_SCHEMA = {
    "type": "object",
    "properties": {"order": {"type": "array", "maxItems": MAX_IDS, "items": {"type": "string"}}},
    "required": ["order"],
}

NOTES_SCHEMA = {
    "type": "object",
    "properties": {
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
    "required": ["notes"],
}

_notes_executor = ThreadPoolExecutor(max_workers=NOTES_WORKERS, thread_name_prefix="notes")


@dataclass
class RerankOutcome:
    ordered: list[Scored]  # the final `limit` results, best first
    notes: dict[str, str]  # window id → note (cached or new) for the ordered windows
    status: str  # "ok" | "skipped:<why>" | "failed"
    new_notes: dict[str, str] = field(default_factory=dict)  # generated for this search and landed in time
    notes_pending: int = 0  # notes still being written in the background when the search answered


def trim_note(text: str, max_words: int = NOTE_MAX_WORDS) -> str:
    """Collapse whitespace; over `max_words`, cut at the last sentence end inside the limit (else hard cut + '…')."""
    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)
    head = " ".join(words[:max_words])
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", head)]
    return head[: ends[-1]] if ends else head.rstrip(",;:") + "…"


def candidate_json(s: Scored, alias: str, *, score: bool = True) -> dict[str, object]:
    c = s.candidate
    out: dict[str, object] = {
        "id": alias,
        "title": c.track["title"],
        "tags": list(c.tags[:CANDIDATE_TAGS]),
        "bpm": round(c.bpm) if c.bpm is not None else None,
        "key": c.track["key"],
        "stem": c.stem,
    }
    if score:
        out["score"] = round(s.score, 2)
    return out


def _header(request: str, chips: Sequence[Chip]) -> str:
    labels = ", ".join(c.label for c in chips) or "none"
    return f"Request: {json.dumps(request, ensure_ascii=False)}\nSelected chips: {labels}\n"


def order_content(request: str, chips: Sequence[Chip], top: Sequence[Scored]) -> str:
    cands = [candidate_json(s, str(i + 1)) for i, s in enumerate(top)]
    return _header(request, chips) + "Candidates:\n" + json.dumps(cands, ensure_ascii=False, separators=(",", ":"))


def notes_content(request: str, chips: Sequence[Chip], windows: Sequence[Scored]) -> str:
    items = [candidate_json(s, str(i + 1), score=False) for i, s in enumerate(windows)]
    return _header(request, chips) + "Windows:\n" + json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def apply_order(top: Sequence[Scored], order: object, limit: int, *, aliases: bool = False) -> list[Scored]:
    """Gemini's order, keeping only real, unseen candidates; then the rest in score order; cut to `limit`.
    With `aliases`, entries are 1-based positions in `top` ("3" or 3); otherwise window ids (the memo)."""
    by_id = {str(i + 1) if aliases else s.candidate.window_id: s for i, s in enumerate(top)}
    picked: list[Scored] = []
    seen: set[str] = set()
    for ref in order if isinstance(order, list) else []:
        key = str(ref).strip() if aliases and isinstance(ref, str | int) and not isinstance(ref, bool) else ref
        if isinstance(key, str) and key in by_id and key not in seen:
            seen.add(key)
            picked.append(by_id[key])
    chosen = {id(s) for s in picked}
    picked += [s for s in top if id(s) not in chosen]
    return picked[:limit]


def parse_notes(raw: object, windows: Sequence[Scored]) -> dict[str, str]:
    """P2b reply → window id → trimmed note. Ids are 1-based aliases into `windows`."""
    by_alias = {str(i + 1): s.candidate.window_id for i, s in enumerate(windows)}
    notes: dict[str, str] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        ref, text = item.get("id"), item.get("note")
        wid = by_alias.get(str(ref).strip()) if isinstance(ref, str | int) and not isinstance(ref, bool) else None
        if wid and isinstance(text, str) and text.strip() and wid not in notes:
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


class _Pending:
    """Notes being generated in the background: window id → the future of its batch (window id → note).

    A window is in at most one batch, so concurrent searches don't ask for the same note twice, and POST /why
    waits for a pending note instead of generating its own. Entries leave when the batch finishes; by then its
    notes are in the `notes` table (written before the future resolves)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._futures: dict[str, Future[dict[str, str]]] = {}

    def claim(self, window_ids: Sequence[str], start: Callable[[list[str]], Future[dict[str, str]]]) -> list[str]:
        """Start `start(claimed)` for the ids not already pending; returns the claimed ids."""
        with self._lock:
            claimed = [w for w in window_ids if w not in self._futures]
            if not claimed:
                return []
            future: Future[dict[str, str]] = start(claimed)
            for w in claimed:
                self._futures[w] = future
        future.add_done_callback(lambda _: self._release(claimed, future))
        return claimed

    def _release(self, window_ids: Sequence[str], future: Future[dict[str, str]]) -> None:
        with self._lock:
            for w in window_ids:
                if self._futures.get(w) is future:
                    del self._futures[w]

    def futures(self, window_ids: Sequence[str]) -> dict[str, Future[dict[str, str]]]:
        with self._lock:
            return {w: self._futures[w] for w in window_ids if w in self._futures}

    def wait(self, window_id: str, timeout_s: float) -> str | None:
        """The pending note for `window_id` once its batch finishes (within `timeout_s`), else None."""
        future = self.futures([window_id]).get(window_id)
        if future is None:
            return None
        try:
            return future.result(timeout=timeout_s).get(window_id)
        except FutureTimeout:
            return None
        except Exception:  # the batch failed; the caller generates its own note
            return None

    def clear(self) -> None:
        with self._lock:
            self._futures.clear()


pending = _Pending()


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


def _make_notes(
    request: str, chips: Sequence[Chip], windows: Sequence[Scored], gemini: Gemini, pool: ConnectionPool
) -> dict[str, str]:
    """P2b, run on the notes pool: generate, store, return. Raises GeminiUnavailable (the future carries it)."""
    raw = gemini.generate_json(
        system=NOTES_SYSTEM,
        contents=notes_content(request, chips, windows),
        schema=NOTES_SCHEMA,
        temperature=RERANK_TEMPERATURE,
        budget=NOTES_BUDGET,
        what="notes",
        timeouts_degrade=False,
    )
    notes = parse_notes(raw.get("notes"), windows)
    if notes:
        try:
            write_notes(pool, notes, f"{gemini.model}:meta")
        except Exception:
            log.warning("notes write failed", exc_info=True)
    return notes


def rerank(
    request: str,
    chips: Sequence[Chip],
    ranked: Sequence[Scored],
    limit: int,
    *,
    gemini: Gemini | None,
    pool: ConnectionPool,
    notes_until: float | None = None,
) -> RerankOutcome:
    """`notes_until`: monotonic deadline for waiting on background notes (None = wait until they're done)."""
    top = list(ranked[:TOP_N])
    cached = _cached(top)
    key = order_key(request, chips, limit, top)
    memo = order_memo.get(key)
    # Without a fresh order, use the one Gemini gave last time for exactly this request and candidate set,
    # else the score order.
    fallback_order = apply_order(top, memo, limit) if memo is not None else top[:limit]

    def keep(status: str) -> RerankOutcome:
        return RerankOutcome(fallback_order, _cached(fallback_order), status)

    if len(top) <= 1:
        return keep("skipped:few")
    if all(s.candidate.window_id in cached for s in fallback_order):
        return keep("skipped:memo" if memo is not None else "skipped:cached")
    if memo is not None and all(s.candidate.window_id in cached for s in fallback_order[:NOTES_PER_RERANK]):
        # Gemini already ordered this exact candidate set and its top results have notes: the rest are /why's job.
        return keep("skipped:memo")
    if gemini is None:
        return keep("skipped:no_client")
    if not gemini.available():
        return keep("skipped:degraded")

    if memo is not None:
        ordered, status = fallback_order, "skipped:memo"
    else:
        try:
            raw = gemini.generate_json(
                system=ORDER_SYSTEM_TEMPLATE.format(limit=min(limit, len(top))),
                contents=order_content(request, chips, top),
                schema=ORDER_SCHEMA,
                temperature=RERANK_TEMPERATURE,
                budget=ORDER_BUDGET,
                what="rerank",
                timeouts_degrade=False,  # missing our own budget is not an outage; don't switch Gemini off for all
            )
        except GeminiUnavailable:
            return keep("failed")
        ordered, status = apply_order(top, raw.get("order"), limit, aliases=True), "ok"
        order_memo.put(key, [s.candidate.window_id for s in ordered])

    # P2b in the background for the top uncached windows; wait for them (and for notes other searches are
    # already writing for these windows) until the deadline.
    want = [s for s in ordered if s.candidate.window_id not in cached][:NOTES_PER_RERANK]
    by_id = {s.candidate.window_id: s for s in want}
    if gemini.available():
        pending.claim(
            list(by_id),
            lambda ids: _notes_executor.submit(_make_notes, request, chips, [by_id[w] for w in ids], gemini, pool),
        )
    futures = pending.futures([s.candidate.window_id for s in ordered if s.candidate.window_id not in cached])
    timeout = None if notes_until is None else max(0.0, notes_until - time.monotonic())
    wait_futures(set(futures.values()), timeout=timeout)
    new: dict[str, str] = {}
    for wid, future in futures.items():
        if future.done() and not future.cancelled() and future.exception() is None:
            text = future.result().get(wid)
            if text:
                new[wid] = text
    ids = [s.candidate.window_id for s in ordered]
    notes = {wid: cached.get(wid) or new.get(wid) for wid in ids}
    late = sum(1 for f in futures.values() if not f.done())
    return RerankOutcome(ordered, {k: v for k, v in notes.items() if v}, status, new, late)
