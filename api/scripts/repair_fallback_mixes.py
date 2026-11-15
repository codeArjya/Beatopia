"""Re-encode API-materialized fallback mixes to the contract format (issue #13, WS1 full report).

Before the fix, `POST /tracks/fs_*/stems` stored the Freesound preview bytes as they were, so the mix wasn't the
CONTRACT §2 format (44.1 kHz stereo MP3 192k) that every ingested mix has. This finds API-materialized tracks
(`source = 'freesound'` with no windows: ingest always writes windows), probes their public `mix.mp3`, and with
`--apply` re-encodes the same audio with `common.audio.to_mp3` and overwrites the object. The old bytes are kept
in `--backup-dir` first. Their stems were separated from the same audio, so they stay valid; `duration_s` is only
updated when the re-encoded mix differs by more than 50 ms.

    uv run --project api --env-file .env python api/scripts/repair_fallback_mixes.py            # dry run
    uv run --project api --env-file .env python api/scripts/repair_fallback_mixes.py --apply
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.fallback import MIX_BITRATE  # noqa: E402
from common import audio, storage  # noqa: E402

WANT = {"codec_name": "mp3", "sample_rate": "44100", "channels": 2, "bit_rate": "192000"}
DURATION_SLACK_S = 0.05


def probe(path: Path) -> dict[str, object]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name,sample_rate,channels,bit_rate", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return json.loads(out.stdout)["streams"][0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="re-encode and overwrite (default: report only)")
    ap.add_argument("--backup-dir", default="fallback-mix-backup", help="where the old bytes are kept")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252

    import os

    with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as conn:
        rows = conn.execute(
            "select t.id, t.audio_path, t.duration_s from tracks t where t.source = 'freesound'"
            " and not exists (select 1 from windows w where w.track_id = t.id) order by t.id"
        ).fetchall()
        print(f"{len(rows)} API-materialized fallback track(s)")
        bad = 0
        backup = Path(args.backup_dir)
        with httpx.Client(timeout=30, follow_redirects=True) as http, tempfile.TemporaryDirectory() as work:
            for track_id, path, duration in rows:
                old = Path(work) / f"{track_id}.old.mp3"
                old.write_bytes(http.get(storage.public_url(path)).raise_for_status().content)
                got = probe(old)
                ok = all(got.get(k) == v for k, v in WANT.items())
                print(f"{track_id}: {path} {got} {'ok' if ok else 'NOT contract format'}")
                if ok:
                    continue
                bad += 1
                if not args.apply:
                    continue
                backup.mkdir(parents=True, exist_ok=True)
                (backup / f"{track_id}.mix.mp3").write_bytes(old.read_bytes())
                new = Path(work) / f"{track_id}.mix.mp3"
                audio.to_mp3(str(old), str(new), MIX_BITRATE)
                after = probe(new)
                if not all(after.get(k) == v for k, v in WANT.items()):
                    print(f"  re-encode still not contract format: {after}; skipped")
                    continue
                y, sr = audio.load_mono(str(new))
                measured = round(len(y) / sr, 3)
                storage.upload(str(new), path, "audio/mpeg")
                if abs(measured - float(duration)) > DURATION_SLACK_S:
                    conn.execute("update tracks set duration_s = %s where id = %s", (measured, track_id))
                print(
                    f"  re-encoded and uploaded ({after}); duration {duration} -> {measured} s; old bytes in {backup}"
                )
        conn.commit()
    print(f"{bad} not in contract format{'' if args.apply else ' (dry run; --apply to fix)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
