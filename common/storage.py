"""Supabase Storage helpers for the public bucket `audio` (CONTRACT §2, §4)."""

import os
from urllib.parse import quote

BUCKET = "audio"


def upload(local_path: str, path: str, content_type: str) -> str:
    """Upload (upsert) `local_path` to `audio/{path}` with the service role key. Returns the public URL."""
    raise NotImplementedError("WS1: common.storage.upload")


def public_url(path: str) -> str:
    """`{SUPABASE_URL}/storage/v1/object/public/audio/{path}`."""
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SUPABASE_URL is not set")
    return f"{base}/storage/v1/object/public/{BUCKET}/{quote(path.lstrip('/'), safe='/')}"
