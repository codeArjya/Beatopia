"""Desktop imports (CONTRACT §2 paths, §6 `POST /imports`).

Flow: stream the upload to a temp file (≤ 25 MB) → check extension + magic bytes → upload the original to
`imports/{id}/original.{ext}` → insert a placeholder `tracks` row (source 'import', private: never searched) and an
`analyze` job in one transaction. WS1's worker fills in the row (duration, bpm, key, beats, `mix.mp3`, windows).
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import PurePath

import psycopg
from psycopg.types.json import Jsonb

from app.core.errors import ApiException, bad_request

log = logging.getLogger("app.imports")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
CHUNK = 1024 * 1024
CONTENT_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
}
PLACEHOLDER_LICENSE = "user-upload"
MAX_TITLE = 120


def too_large() -> ApiException:
    return ApiException("upload_too_large", f"files are limited to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")


def unsupported(message: str) -> ApiException:
    return ApiException("unsupported_format", message)


def extension(filename: str | None) -> str:
    ext = PurePath(filename or "").suffix.lower().lstrip(".")
    if ext not in CONTENT_TYPES:
        raise unsupported(f"unsupported file type {'.' + ext if ext else '(none)'}; use wav, mp3, flac, m4a or ogg")
    return ext


def sniff(head: bytes) -> str | None:
    """Container type from the first bytes, or None. mp3 = ID3 tag or an MPEG audio frame sync."""
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        return "ogg"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "mp3"
    return None


def title_from(filename: str | None) -> str:
    stem = PurePath(filename or "").stem
    title = re.sub(r"[\x00-\x1f\x7f]+", " ", stem)
    title = re.sub(r"[_\s]+", " ", title).strip()
    return title[:MAX_TITLE] or "Untitled import"


def new_track_id() -> str:
    return f"imp_{secrets.token_hex(4)}"


@dataclass
class Spooled:
    path: str
    size: int
    head: bytes


async def spool(read: Callable[[int], Awaitable[bytes]], limit: int | None = None) -> Spooled:
    """Copy the upload to a temp file, failing with upload_too_large as soon as it passes `limit`."""
    limit = MAX_UPLOAD_BYTES if limit is None else limit
    fd, path = tempfile.mkstemp(prefix="beatopia-import-")
    size, head = 0, b""
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise too_large()
                if len(head) < 16:
                    head = (head + chunk)[:16]
                out.write(chunk)
    except BaseException:
        os.unlink(path)
        raise
    if size == 0:
        os.unlink(path)
        raise bad_request("the uploaded file is empty")
    return Spooled(path=path, size=size, head=head)


def check_format(ext: str, head: bytes) -> None:
    kind = sniff(head)
    if kind is None:
        raise unsupported("the file does not look like audio (wav, mp3, flac, m4a or ogg)")
    if kind != ext:
        raise unsupported(f"the file is named .{ext} but looks like {kind}")


def create_import(conn: psycopg.Connection, track_id: str, title: str, original_path: str) -> str:
    """Placeholder track row + `analyze` job in one transaction. Returns the job id."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "insert into tracks (id, source, title, license, attribution, duration_s, audio_path)"
            " values (%s, 'import', %s, %s, '', 0, %s)",
            (track_id, title, PLACEHOLDER_LICENSE, f"imports/{track_id}/mix.mp3"),
        )
        row = cur.execute(
            "insert into jobs (kind, input) values ('analyze', %s) returning id",
            (Jsonb({"track_id": track_id, "path": original_path}),),
        ).fetchone()
    assert row is not None
    log.info("import %s (%s) queued as analyze job %s", track_id, original_path, row[0])
    return str(row[0])
