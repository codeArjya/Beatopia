"""SearchPlan building (CONTRACT §7.1): Gemini planner (prompt P1) + plan_cache, then the deterministic chip merge.

Chips are merged AFTER the plan, so chips always apply. Text-less (chips-only) searches never call Gemini. Any Gemini
failure gives `base_plan` (the raw text as CLAP caption, no filters), which is not cached.

Cache: sha256(normalized text | sorted chip ids) → the pre-merge plan, in `plan_cache` plus an in-process LRU in
front of it (the session pooler round trip alone is 80–170 ms).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from app.core.chips import KEYS, chip_index, parse_vocab
from app.core.errors import bad_request
from app.core.gemini import CallBudget, Gemini, GeminiUnavailable
from app.models.api import Chip, SearchPlan

log = logging.getLogger("app.planner")

CAPTION_CATEGORIES = ("instrument", "genre", "mood")  # tempo/key chips never go into the CLAP caption
GENERIC_CAPTION = "music"

PLAN_BUDGET = CallBudget(timeout_ms=4_000, attempts=2)
PLAN_TEMPERATURE = 0.2
SINGLE_BPM_HALF_WIDTH = 5.0
MAX_MUST_TAGS = 4
MAX_EXCLUDE_TAGS = 12
STEMS = ["vocals", "drums", "bass", "other", "guitar", "piano"]
MEMORY_CACHE_SIZE = 1024

PlanSource = Literal["chips", "memory", "db", "gemini", "fallback"]


def normalize_text(text: str | None) -> str | None:
    text = " ".join((text or "").split())
    return text or None


def resolve_chips(chip_ids: Sequence[str], vocab_path: Path) -> list[Chip]:
    index = chip_index(vocab_path)
    unknown = [c for c in chip_ids if c not in index]
    if unknown:
        raise bad_request(f"unknown chip id(s): {', '.join(unknown)} (use the ids from GET /chips)")
    return [index[c] for c in chip_ids]


def chip_caption(chips: Sequence[Chip]) -> str:
    """'trumpet, soul, melancholy music' from the instrument/genre/mood chips; 'music' if there are none."""
    labels = [c.label.lower() for c in chips if c.category in CAPTION_CATEGORIES]
    return f"{', '.join(labels)} {GENERIC_CAPTION}" if labels else GENERIC_CAPTION


def base_plan(text: str | None, chips: Sequence[Chip]) -> SearchPlan:
    """The plan without Gemini (also the fallback when Gemini fails): CLAP caption only, no filters."""
    return SearchPlan(clap_text=text or chip_caption(chips))


def merge_chips(plan: SearchPlan, chips: Sequence[Chip]) -> SearchPlan:
    """Chip tags → must_tags (and out of exclude_tags); tempo chips → min(lo)..max(hi); last key chip wins."""
    chip_tags = [t for c in chips for t in c.filter.tags]
    must = list(dict.fromkeys([*plan.must_tags, *chip_tags]))
    exclude = [t for t in plan.exclude_tags if t not in set(chip_tags)]
    ranges = [c.filter.bpm_range for c in chips if c.filter.bpm_range is not None]
    bpm_range = (min(lo for lo, _ in ranges), max(hi for _, hi in ranges)) if ranges else plan.bpm_range
    keys = [c.filter.key for c in chips if c.filter.key]
    return plan.model_copy(
        update={
            "must_tags": must,
            "exclude_tags": exclude,
            "bpm_range": bpm_range,
            "key": keys[-1] if keys else plan.key,
        }
    )


# ---- P1: prompt and Gemini-facing schema ----

SYSTEM_TEMPLATE = """\
You turn a music producer's search request into a search plan for a library of Creative Commons
music, cut into short windows (about 4 to 16 bars). Each window is tagged automatically with tags from a
fixed vocabulary and matched against your "clap_text" with a CLAP audio-text embedding model.

Write the plan so the right windows come back:

clap_text: one short English description of how the sound should SOUND, as a caption for an audio clip
  (for example "a melancholy solo trumpet over soft jazz chords, slow tempo"). Describe instruments,
  timbre, mood, genre and texture. Do not include BPM numbers, keys, artist names, song titles, or words
  like "sample", "loop" or "find me". Under 25 words.
must_tags: tags the window MUST have. Use only tags from the vocabulary below. Add a tag only when the
  user clearly asks for it (an instrument they name, a genre they name). Prefer 0 to 2 tags; when in
  doubt, put the idea in clap_text instead. Never put moods in must_tags unless the user insists.
exclude_tags: tags the window must NOT have, only when the user says so ("no drums", "without vocals").
  Expand an exclusion to the related tags: "no drums" means drum loop, breakbeat, kick, snare, hi-hats,
  cymbals; "no vocals" means female vocals, male vocals, vocal chop, choir, spoken word, humming.
  Only use tags that are in the vocabulary.
bpm_min / bpm_max: only if the user mentions tempo. A single number N means N-5 to N+5. "slow" means 60
  to 85, "mid-tempo" 85 to 110, "fast" 120 to 170. Otherwise null.
key: only if the user names a key, written exactly like "A minor" or "F# major" (use sharps, never
  flats: Bb becomes A#). Otherwise null.
stems_wanted: only if the user explicitly asks to ISOLATE a part from a song: "just the drums" or
  "drums only" means ["drums"], "acapella" or "vocals only" means ["vocals"], "isolated bass" or "just
  the bass" means ["bass"], "just the horns/keys/melody" means ["other"]. Few tracks have separated
  parts, so naming an instrument is NOT a request for a stem: "drum break", "bass line", "piano chords",
  "soul vocals" all mean []. Otherwise [].
prefer_sparse: true only if the user asks for a clean, open, isolated or minimal moment ("clean",
  "solo", "just the", "sparse", "exposed", "breakdown", "intro"). An instrument or genre name alone is
  not a reason. Otherwise false.

The user may also have selected filter chips. Chips are applied by the system AFTER you answer, so do
not repeat them; but do keep clap_text consistent with them (if a "soul" chip is selected, the
description should sound like soul).

If the request is vague ("something cool"), write a reasonable clap_text and leave everything else empty.
If the request is not about music, still return a valid plan with a generic clap_text.

Vocabulary (use these strings exactly):
instruments: {instrument}
genres: {genre}
moods: {mood}
"""


@cache
def vocab_tags(vocab_path: Path) -> tuple[str, ...]:
    return tuple(t for tags in parse_vocab(vocab_path).values() for t in tags)


@cache
def system_prompt(vocab_path: Path) -> str:
    vocab = parse_vocab(vocab_path)
    return SYSTEM_TEMPLATE.format(**{k: ", ".join(v) for k, v in vocab.items()})


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


@cache
def plan_schema() -> dict[str, Any]:
    """Flat schema for Gemini: bpm_min/bpm_max instead of the bpm_range tuple; key and stems as enums.

    Tags are plain strings: two 126-value tag enums make the API answer `400 INVALID_ARGUMENT` (checked live on
    2026-11-14). The prompt lists the vocab, and `from_gemini` drops anything outside it.
    """
    tag = {"type": "string", "description": "A tag from the vocabulary, spelled exactly."}
    bpm = _nullable({"type": "number", "minimum": 40, "maximum": 240})
    props: dict[str, Any] = {
        "clap_text": {"type": "string", "description": "Audio caption, under 25 words."},
        "must_tags": {"type": "array", "maxItems": MAX_MUST_TAGS, "items": tag},
        "exclude_tags": {"type": "array", "maxItems": MAX_EXCLUDE_TAGS, "items": tag},
        "bpm_min": bpm,
        "bpm_max": bpm,
        "key": _nullable({"type": "string", "enum": KEYS}),
        "stems_wanted": {"type": "array", "items": {"type": "string", "enum": STEMS}},
        "prefer_sparse": {"type": "boolean"},
    }
    return {"type": "object", "properties": props, "required": list(props)}


def user_content(text: str, chips: Sequence[Chip]) -> str:
    labels = ", ".join(c.label for c in chips) or "none"
    return f"Request: {json.dumps(text, ensure_ascii=False)}\nSelected chips: {labels}"


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if 40 <= value <= 240 else None


def _tags(value: Any, allowed: set[str], limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(t for t in value if isinstance(t, str) and t in allowed))[:limit]


def from_gemini(raw: dict[str, Any], *, fallback_text: str, vocab_path: Path) -> SearchPlan:
    """Gemini's flat JSON → SearchPlan, defensively (tags/keys/stems filtered again, bpm sanity-checked)."""
    allowed = set(vocab_tags(vocab_path))
    clap_text = normalize_text(raw.get("clap_text") if isinstance(raw.get("clap_text"), str) else None)
    lo, hi = _num(raw.get("bpm_min")), _num(raw.get("bpm_max"))
    if lo is not None and hi is not None:
        bpm_range: tuple[float, float] | None = (min(lo, hi), max(lo, hi))
    elif lo is not None or hi is not None:
        n = lo if lo is not None else hi
        assert n is not None
        bpm_range = (n - SINGLE_BPM_HALF_WIDTH, n + SINGLE_BPM_HALF_WIDTH)
    else:
        bpm_range = None
    must = _tags(raw.get("must_tags"), allowed, MAX_MUST_TAGS)
    exclude = [t for t in _tags(raw.get("exclude_tags"), allowed, MAX_EXCLUDE_TAGS) if t not in must]
    key = raw.get("key") if raw.get("key") in KEYS else None
    stems = raw.get("stems_wanted") if isinstance(raw.get("stems_wanted"), list) else []
    return SearchPlan(
        clap_text=clap_text or fallback_text,
        must_tags=must,
        exclude_tags=exclude,
        bpm_range=bpm_range,
        key=key,
        stems_wanted=[s for s in dict.fromkeys(stems) if s in STEMS],
        prefer_sparse=raw.get("prefer_sparse") is True,
    )


# ---- cache ----


def cache_key(text: str, chip_ids: Sequence[str]) -> str:
    norm = " ".join(text.lower().split())
    return hashlib.sha256(f"{norm}|{','.join(sorted(chip_ids))}".encode()).hexdigest()


class _Lru:
    def __init__(self, size: int) -> None:
        self.size = size
        self._data: OrderedDict[str, SearchPlan] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> SearchPlan | None:
        with self._lock:
            plan = self._data.get(key)
            if plan is not None:
                self._data.move_to_end(key)
            return plan

    def put(self, key: str, plan: SearchPlan) -> None:
        with self._lock:
            self._data[key] = plan
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


memory_cache = _Lru(MEMORY_CACHE_SIZE)


def db_get(pool: ConnectionPool, key: str) -> SearchPlan | None:
    with pool.connection() as conn:
        row = conn.execute("select plan from plan_cache where hash = %s", (key,)).fetchone()
    if row is None:
        return None
    try:
        return SearchPlan.model_validate(row[0])
    except ValidationError:
        log.warning("ignoring an invalid plan_cache row %s", key[:12])
        return None


def db_put(pool: ConnectionPool, key: str, plan: SearchPlan) -> None:
    with pool.connection() as conn:
        conn.execute(
            "insert into plan_cache (hash, plan) values (%s, %s)"
            " on conflict (hash) do update set plan = excluded.plan, created_at = now()",
            (key, Jsonb(plan.model_dump(mode="json"))),
        )


# ---- entry point ----


@dataclass(frozen=True)
class PlanOutcome:
    plan: SearchPlan  # chips already merged
    source: PlanSource

    @property
    def cached(self) -> bool:
        return self.source in ("memory", "db")


def make_plan(
    text: str | None,
    chips: Sequence[Chip],
    chip_ids: Sequence[str],
    *,
    pool: ConnectionPool,
    gemini: Gemini | None,
    vocab_path: Path,
) -> PlanOutcome:
    if text is None:  # chips only: nothing for Gemini to interpret
        return PlanOutcome(merge_chips(base_plan(None, chips), chips), "chips")

    key = cache_key(text, chip_ids)
    source: PlanSource
    plan = memory_cache.get(key)
    source = "memory"
    if plan is None:
        try:
            plan = db_get(pool, key)
        except Exception:
            log.warning("plan_cache read failed", exc_info=True)
            plan = None
        source = "db"
        if plan is not None:
            memory_cache.put(key, plan)
    if plan is None:
        plan, source = _ask_gemini(text, chips, gemini, vocab_path)
        if source == "gemini":
            memory_cache.put(key, plan)
            try:
                db_put(pool, key, plan)
            except Exception:
                log.warning("plan_cache write failed", exc_info=True)
    return PlanOutcome(merge_chips(plan, chips), source)


def _ask_gemini(
    text: str, chips: Sequence[Chip], gemini: Gemini | None, vocab_path: Path
) -> tuple[SearchPlan, PlanSource]:
    if gemini is None:
        return base_plan(text, chips), "fallback"
    try:
        raw = gemini.generate_json(
            system=system_prompt(vocab_path),
            contents=user_content(text, chips),
            schema=plan_schema(),
            temperature=PLAN_TEMPERATURE,
            budget=PLAN_BUDGET,
            what="planner",
        )
    except GeminiUnavailable:
        return base_plan(text, chips), "fallback"
    return from_gemini(raw, fallback_text=text, vocab_path=vocab_path), "gemini"
