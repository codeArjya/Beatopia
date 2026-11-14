"""Supabase Storage helpers for the public bucket `audio` (CONTRACT §2, §4)."""

import os
from urllib.parse import quote

from supabase import create_client

BUCKET = "audio"


def upload(local_path: str, path: str, content_type: str) -> str:
    """Upload (upsert) `local_path` to `audio/{path}` with the service role key. Returns the public URL."""
    url = public_url(path)
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set")
    client = create_client(os.environ["SUPABASE_URL"].rstrip("/"), key)
    with client.storage as storage, open(local_path, "rb") as audio:
        storage.from_(BUCKET).upload(
            path=path.lstrip("/"),
            file=audio,
            file_options={"content-type": content_type, "upsert": "true"},
        )
    return url


def public_url(path: str) -> str:
    """`{SUPABASE_URL}/storage/v1/object/public/audio/{path}`."""
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SUPABASE_URL is not set")
    return f"{base}/storage/v1/object/public/{BUCKET}/{quote(path.lstrip('/'), safe='/')}"
