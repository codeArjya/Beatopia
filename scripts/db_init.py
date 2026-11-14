"""Apply db/migrations/*.sql in order and create the public Storage bucket "audio" if missing.

    uv run --project common python scripts/db_init.py            # apply + bucket
    uv run --project common python scripts/db_init.py --dry-run  # show what would run

Idempotent: applied migrations are recorded in `schema_migrations`, and the bucket is only created if absent.
Reads DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY from the environment or the repo-root .env.
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "db" / "migrations"
BUCKET = "audio"


def load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE, # comments); never overrides variables already set."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} is not set (put it in .env)")
    return value


def apply_migrations(dry_run: bool) -> None:
    files = sorted(MIGRATIONS.glob("*.sql"))
    with psycopg.connect(require("DATABASE_URL"), autocommit=True) as conn:
        conn.execute(
            "create table if not exists schema_migrations ("
            " name text primary key, applied_at timestamptz not null default now())"
        )
        applied = {row[0] for row in conn.execute("select name from schema_migrations")}
        for f in files:
            if f.name in applied:
                print(f"skip   {f.name}")
                continue
            print(f"{'would apply' if dry_run else 'apply'}  {f.name}")
            if dry_run:
                continue
            with conn.transaction():
                conn.execute(f.read_text(encoding="utf-8"))
                conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))


def ensure_bucket(dry_run: bool) -> None:
    client = create_client(require("SUPABASE_URL"), require("SUPABASE_SERVICE_ROLE_KEY"))
    existing = {b.id for b in client.storage.list_buckets()}
    if BUCKET in existing:
        print(f"bucket '{BUCKET}' exists")
        return
    print(f"{'would create' if dry_run else 'create'} public bucket '{BUCKET}'")
    if not dry_run:
        client.storage.create_bucket(BUCKET, options={"public": True})


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply migrations and create the audio bucket.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    apply_migrations(args.dry_run)
    ensure_bucket(args.dry_run)


if __name__ == "__main__":
    main()
