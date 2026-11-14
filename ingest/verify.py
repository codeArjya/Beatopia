"""Read-only corpus/checkpoint verification, until the quality reporter exists."""

import argparse
import json
from pathlib import Path

import httpx

from common import db
from ingest.pipeline import published, validate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("ingest/data"))
    parser.add_argument("--minimum", type=int, default=0)
    args = parser.parse_args()
    report: dict[str, object] = {}
    with db.connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        report["counts"] = dict(
            conn.execute(
                "SELECT 'tracks', count(*) FROM tracks UNION ALL SELECT 'windows',count(*) FROM windows "
                "UNION ALL SELECT 'stems',count(*) FROM stems"
            ).fetchall()
        )
        report["sources_licenses"] = conn.execute(
            "SELECT source,license,count(*) FROM tracks GROUP BY source,license ORDER BY source,license"
        ).fetchall()
        report["invalid_windows"] = conn.execute(
            "SELECT count(*) FROM windows w JOIN tracks t ON t.id=w.track_id "
            "WHERE start_s<0 OR end_s<=start_s OR end_s>duration_s+0.001 OR vector_dims(embedding)<>512 "
            "OR abs(vector_norm(embedding)-1)>0.0001 OR t.attribution='' "
        ).fetchone()[0]
        report["jobs"] = conn.execute("SELECT status,count(*) FROM jobs GROUP BY status").fetchall()
    verified, failures = [], []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for path in sorted((args.data_dir / "tracks").glob("*/manifest.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                vectors = validate(manifest, path.parent)
                if not published(manifest, client, vectors):
                    raise ValueError("DB or public audio mismatch")
                verified.append(manifest["id"])
            except Exception as error:
                failures.append({"id": path.parent.name, "error_type": type(error).__name__})
    report.update(verified_count=len(verified), verified_ids=verified, failures=failures)
    print(json.dumps(report, indent=2))
    if failures or report["invalid_windows"] or len(verified) < args.minimum:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
