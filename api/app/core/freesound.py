"""Freesound API client for the search fallback (CONTRACT §7.7, proposal C10 `docs/proposals/WS2-fallback-trigger.md`).

Same endpoint, auth and license set as WS1's Freesound ingest (`ingest/sources.py`): `GET /apiv2/search/` with a
`Token` header, CC0 and CC BY only. Short sounds (1–30 s) only, because a fallback result plays its first 16 s.
Searches and single sounds are cached in process for an hour. Nothing here touches the DB.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("app.freesound")

API = "https://freesound.org/apiv2"
FIELDS = "id,name,username,license,duration,tags,url,previews"
FILTER = 'license:("Creative Commons 0" OR "Attribution") duration:[1 TO 30]'
TIMEOUT_S = 5.0
CACHE_TTL_S = 3600.0
CACHE_SIZE = 512
MAX_WINDOW_S = 16.0  # a fallback window is 0..min(duration, 16) s (CONTRACT §7.7)
MAX_PREVIEW_BYTES = 20 * 1024 * 1024
MAX_QUERY_CHARS = 100
# Preview URLs go to ffmpeg (/why excerpt) and to the stems copy, so they must point at Freesound itself.
PREVIEW_HOSTS = frozenset({"cdn.freesound.org", "freesound.org"})
CC_HOSTS = frozenset({"creativecommons.org", "www.creativecommons.org"})

TRACK_ID_RE = re.compile(r"^fs_(\d{1,12})$")
WINDOW_ID_RE = re.compile(r"^fs_(\d{1,12}):mix:0$")


class FreesoundError(Exception):
    """Freesound could not be reached or answered with an error (timeout, 5xx, 401, bad JSON)."""


def cc_license(url: str) -> str | None:
    """Freesound license URL → our license string (as WS1 writes it), or None when it isn't CC0 / CC BY."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in CC_HOSTS:
        return None
    if re.fullmatch(r"/publicdomain/zero/1\.0/?", parsed.path):
        return "CC0"
    match = re.fullmatch(r"/licenses/by/(\d\.\d)/?", parsed.path)
    return f"CC-BY-{match[1]}" if match else None


def sound_id(track_or_window_id: str) -> int | None:
    """The Freesound id in a fallback track id `fs_123` or window id `fs_123:mix:0`, else None."""
    match = TRACK_ID_RE.match(track_or_window_id) or WINDOW_ID_RE.match(track_or_window_id)
    return int(match[1]) if match else None


@dataclass(frozen=True)
class Sound:
    id: int
    name: str
    username: str
    license: str
    license_url: str
    url: str
    duration_s: float
    preview_url: str
    tags: tuple[str, ...]  # Freesound tags that are also vocab tags

    @property
    def track_id(self) -> str:
        return f"fs_{self.id}"

    @property
    def window_id(self) -> str:
        return f"fs_{self.id}:mix:0"

    @property
    def window_end_s(self) -> float:
        return round(min(self.duration_s, MAX_WINDOW_S), 3)

    @property
    def attribution(self) -> str:
        # Same shape as WS1's ingested Freesound tracks.
        return f"{self.name} by {self.username}; {self.url}; {self.license} ({self.license_url})"


def _vocab_tags(raw: Any, vocab: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    out: dict[str, None] = {}
    for tag in raw:
        if not isinstance(tag, str):
            continue
        t = tag.strip().lower()
        for variant in (t, t.replace("-", " "), t.replace("_", " ")):
            if variant in vocab:
                out[variant] = None
                break
    return tuple(out)


def parse_sound(raw: Any, vocab: frozenset[str] = frozenset()) -> Sound | None:
    """A Freesound API sound → Sound, or None when it's unusable (license, missing preview, bad fields)."""
    if not isinstance(raw, dict):
        return None
    sid, name, user = raw.get("id"), raw.get("name"), raw.get("username")
    license_url, page, duration = raw.get("license"), raw.get("url"), raw.get("duration")
    previews = raw.get("previews") if isinstance(raw.get("previews"), dict) else {}
    preview = previews.get("preview-hq-mp3") if previews else None
    if not (isinstance(sid, int) and not isinstance(sid, bool) and sid > 0):
        return None
    if not all(isinstance(v, str) and v.strip() for v in (name, user, license_url, page, preview)):
        return None
    if isinstance(duration, bool) or not isinstance(duration, int | float) or not 0 < duration <= 600:
        return None
    lic = cc_license(license_url)
    if lic is None:
        return None
    p = urlsplit(preview)
    if p.scheme != "https" or p.hostname not in PREVIEW_HOSTS:
        return None
    if urlsplit(page).scheme not in {"http", "https"}:
        return None
    return Sound(
        id=sid,
        name=" ".join(name.split()),
        username=user.strip(),
        license=lic,
        license_url=license_url,
        url=page,
        duration_s=float(duration),
        preview_url=preview,
        tags=_vocab_tags(raw.get("tags"), vocab),
    )


K = TypeVar("K")
V = TypeVar("V")


class TtlCache(Generic[K, V]):
    """Small thread-safe LRU whose entries expire after `ttl_s`."""

    def __init__(self, size: int, ttl_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.size, self.ttl_s, self.clock = size, ttl_s, clock
        self._data: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: K) -> V | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            if self.clock() - item[0] > self.ttl_s:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return item[1]

    def put(self, key: K, value: V) -> None:
        with self._lock:
            self._data[key] = (self.clock(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


def normalize_query(text: str) -> str:
    return " ".join(text.lower().split())[:MAX_QUERY_CHARS]


class Freesound:
    """Freesound search + sound lookup with an hour-long in-process cache. One per app (keep-alive client)."""

    def __init__(self, api_key: str, *, vocab: Iterable[str] = (), client: httpx.Client | None = None) -> None:
        self.vocab = frozenset(vocab)
        self.client = client or httpx.Client(timeout=TIMEOUT_S)
        self._headers = {"Authorization": f"Token {api_key}"}
        self.searches: TtlCache[tuple[str, int], tuple[Sound, ...]] = TtlCache(CACHE_SIZE, CACHE_TTL_S)
        self.sounds: TtlCache[int, Sound | None] = TtlCache(CACHE_SIZE * 4, CACHE_TTL_S)

    def close(self) -> None:
        self.client.close()

    def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        try:
            return self.client.get(f"{API}{path}", params=params, headers=self._headers, timeout=TIMEOUT_S)
        except httpx.HTTPError as exc:
            # The message never contains the token (it's a header), but keep it short anyway.
            raise FreesoundError(f"freesound {path.split('/')[1]}: {type(exc).__name__}") from exc

    def search(self, query: str, limit: int) -> list[Sound]:
        """Up to `limit` usable sounds for `query`, in Freesound's relevance order. Raises FreesoundError."""
        q = normalize_query(query)
        if not q:
            return []
        cached = self.searches.get((q, limit))
        if cached is not None:
            return list(cached)
        # Ask for a few extra: some results are dropped (license, preview, a library duplicate).
        r = self._get("/search/", {"query": q, "filter": FILTER, "fields": FIELDS, "page_size": min(limit + 4, 30)})
        if r.status_code != 200:
            raise FreesoundError(f"freesound search: HTTP {r.status_code}")
        try:
            body = r.json()
        except ValueError as exc:
            raise FreesoundError("freesound search: invalid JSON") from exc
        rows = body.get("results") if isinstance(body, dict) else None
        sounds = [s for s in (parse_sound(row, self.vocab) for row in (rows if isinstance(rows, list) else [])) if s]
        sounds = sounds[:limit]
        for s in sounds:
            self.sounds.put(s.id, s)
        self.searches.put((q, limit), tuple(sounds))
        return sounds

    def sound(self, sid: int) -> Sound | None:
        """One sound by id (cache first), or None when it doesn't exist or isn't usable. Raises FreesoundError."""
        cached = self.sounds.get(sid)
        if cached is not None:
            return cached
        r = self._get(f"/sounds/{sid}/", {"fields": FIELDS})
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise FreesoundError(f"freesound sound: HTTP {r.status_code}")
        try:
            sound = parse_sound(r.json(), self.vocab)
        except ValueError as exc:
            raise FreesoundError("freesound sound: invalid JSON") from exc
        if sound is not None:
            self.sounds.put(sid, sound)
        return sound

    def download_preview(self, sound: Sound, dest: str) -> int:
        """Stream the HQ MP3 preview to `dest` (≤ 20 MB). Returns the byte count. Raises FreesoundError."""
        size = 0
        try:
            with self.client.stream("GET", sound.preview_url, timeout=TIMEOUT_S * 3) as r:
                if r.status_code != 200:
                    raise FreesoundError(f"freesound preview: HTTP {r.status_code}")
                with open(dest, "wb") as out:
                    for chunk in r.iter_bytes():
                        size += len(chunk)
                        if size > MAX_PREVIEW_BYTES:
                            raise FreesoundError("freesound preview: too large")
                        out.write(chunk)
        except httpx.HTTPError as exc:
            raise FreesoundError(f"freesound preview: {type(exc).__name__}") from exc
        if size == 0:
            raise FreesoundError("freesound preview: empty")
        return size
