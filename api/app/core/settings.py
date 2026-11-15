"""Server settings, read once from the environment (CONTRACT §8)."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"  # CONTRACT §8 after C9 (PR #6)
DEFAULT_WEB_ORIGIN = "http://localhost:3000"

_TRUE = {"1", "true", "yes", "on"}


def _str(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _flag(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in _TRUE


def _origins(raw: str | None) -> tuple[str, ...]:
    return tuple(o.strip() for o in (raw or DEFAULT_WEB_ORIGIN).split(",") if o.strip())


def origin_regex(origins: tuple[str, ...]) -> str | None:
    """Regex for the WEB_ORIGIN entries that contain `*` (e.g. Vercel previews `https://beatopia-*.vercel.app`).

    `*` matches one or more of `[a-z0-9-]`, so it never crosses a dot: `https://beatopia-*.vercel.app` allows
    `https://beatopia-git-main-team.vercel.app` but not `https://beatopia-x.evil.com/.vercel.app`.
    """
    patterns = [re.escape(o).replace(r"\*", "[a-z0-9-]+") for o in origins if "*" in o]
    return f"^(?:{'|'.join(patterns)})$" if patterns else None


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    supabase_url: str | None
    supabase_service_role_key: str | None
    gemini_api_key: str | None
    gemini_model: str
    gemini_degraded: bool
    freesound_api_key: str | None
    clap_model: str
    demucs_model: str
    web_origins: tuple[str, ...]
    use_fixtures: bool
    fixtures_dir: Path
    vocab_path: Path
    revision: str = "dev"  # git sha baked into the image by deploy.sh (BEATOPIA_REVISION)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            database_url=_str(env, "DATABASE_URL"),
            supabase_url=_str(env, "SUPABASE_URL"),
            supabase_service_role_key=_str(env, "SUPABASE_SERVICE_ROLE_KEY"),
            gemini_api_key=_str(env, "GEMINI_API_KEY"),
            gemini_model=_str(env, "GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
            gemini_degraded=_flag(env, "GEMINI_DEGRADED"),
            freesound_api_key=_str(env, "FREESOUND_API_KEY"),
            clap_model=_str(env, "CLAP_MODEL") or "laion/larger_clap_music",
            demucs_model=_str(env, "DEMUCS_MODEL") or "htdemucs",
            web_origins=_origins(_str(env, "WEB_ORIGIN")),
            use_fixtures=_flag(env, "USE_FIXTURES"),
            fixtures_dir=Path(_str(env, "FIXTURES_DIR") or REPO_ROOT / "shared" / "fixtures"),
            vocab_path=REPO_ROOT / "ingest" / "vocab.txt",
            revision=_str(env, "BEATOPIA_REVISION") or "dev",
        )

    def missing(self, *names: str) -> list[str]:
        """Env var names (upper case) among `names` (field names) that are unset."""
        known = {f.name for f in fields(self)}
        unknown = set(names) - known
        if unknown:
            raise ValueError(f"unknown settings: {sorted(unknown)}")
        return [n.upper() for n in names if getattr(self, n) is None]


@cache
def get_settings() -> Settings:
    return Settings.from_env()
