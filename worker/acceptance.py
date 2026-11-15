"""Explicit live acceptance runner. Inserts only its own jobs; never polls others.

Run with the same model/cache environment as the worker, from the repo root.
Artifacts/checkpoints stay in worker/data. Failed jobs are retained, never relabeled.
"""

import json
import time
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from psycopg.types.json import Jsonb

from common import db, storage
from worker import jobs
from worker.handlers import digest, write_json
from worker.main import run_job


def enqueue(kind: str, data: dict) -> str:
    with db.connect() as conn:
        row = conn.execute("INSERT INTO jobs(kind,input) VALUES(%s,%s) RETURNING id", (kind, Jsonb(data))).fetchone()
    return str(row[0])


def execute(kind: str, data: dict, root: Path) -> dict:
    started = time.perf_counter()
    jid = enqueue(kind, data)
    job = jobs.claim(jid)
    if job is None:
        raise ValueError("Acceptance job was not claimable")
    run_job(job, root)
    with db.connect() as conn:
        row = conn.execute("SELECT status,progress,output,error FROM jobs WHERE id=%s", (jid,)).fetchone()
    record = {
        "job_id": jid,
        "status": row[0],
        "progress": row[1],
        "output": row[2],
        "error": row[3],
        "enqueue_claim_process_poll_s": time.perf_counter() - started,
    }
    with (root / "acceptance-jobs.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(record, allow_nan=False) + "\n")
    if row[0] != "done" or row[1] != 1 or row[3] is not None:
        raise ValueError(f"Acceptance job {jid} ended as {row[0]}; inspect worker/data logs")
    return record


def main() -> None:
    # Model definitions are read-only; the production worker has no API package dependency.
    from api.app.models.api import AnalyzeJobOutput, StemsJobOutput

    root = Path("worker/data")
    root.mkdir(parents=True, exist_ok=True)
    report_path = root / "acceptance-session4.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    report["runtime"] = {
        "torch": torch.__version__,
        "cuda": torch.cuda.is_available(),
        "mps": torch.backends.mps.is_available(),
    }
    tid = report.setdefault("import_id", "imp_" + uuid.uuid4().hex[:8])
    write_json(report_path, report)
    original = root / "acceptance-original.wav"
    if not original.exists():
        # Public synthetic fixture, real analysis and CLAP. Never presented as a licensed corpus track.
        fixture = Path("web/public/fixtures/audio/mix.wav")
        samples, sr = sf.read(fixture, dtype="float32", always_2d=True)
        sf.write(original, samples, sr)
    original_path = f"imports/{tid}/original.wav"
    storage.upload(str(original), original_path, "audio/wav")
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO tracks(id,source,title,artist,license,attribution,duration_s,audio_path)
               VALUES(%s,'import','Session 4 synthetic acceptance import','Beatopia',
               'user-upload','Synthetic acceptance fixture, uploaded by Beatopia',0,%s) ON CONFLICT(id) DO NOTHING""",
            (tid, original_path),
        )
    if "import" not in report:
        result = execute("analyze", {"track_id": tid, "path": original_path}, root)
        detail = AnalyzeJobOutput.model_validate(result["output"]).track
        assert detail.track.source == "import" and detail.track.license == "user-upload"
        assert detail.track.title == "Session 4 synthetic acceptance import"
        assert detail.track.attribution == "Synthetic acceptance fixture, uploaded by Beatopia"
        assert len(detail.windows) == 3 and detail.track.duration_s == 16
        with db.connect() as conn:
            rows = conn.execute("SELECT embedding FROM windows WHERE track_id=%s", (tid,)).fetchall()
            assert len(rows) == 3 and all(np.isclose(np.linalg.norm(row[0].to_numpy()), 1) for row in rows)
        report["import"] = result
        write_json(report_path, report)
    if "import_repeat" not in report:
        before = digest(root / "imports" / tid / "mix.mp3")
        report["import_repeat"] = execute("analyze", {"track_id": tid, "path": original_path}, root)
        assert digest(root / "imports" / tid / "mix.mp3") == before
        with db.connect() as conn:
            assert conn.execute("SELECT count(*) FROM windows WHERE track_id=%s", (tid,)).fetchone()[0] == 3
        write_json(report_path, report)
    if "stem_track" not in report:
        with db.connect() as conn:
            row = conn.execute(
                """SELECT t.id FROM tracks t WHERE source='freesound' AND duration_s>=45 AND NOT is_hero
                   AND NOT EXISTS(SELECT 1 FROM stems s WHERE s.track_id=t.id) ORDER BY t.id LIMIT 1"""
            ).fetchone()
        if row is None:
            raise ValueError("No eligible uncached real 30-second track")
        report["stem_track"] = row[0]
        write_json(report_path, report)
    data = {"track_id": report["stem_track"], "start_s": 5, "end_s": 35, "model": "htdemucs"}
    if "stems_30s" not in report:
        result = execute("stems", data, root)
        output = StemsJobOutput.model_validate(result["output"])
        assert len(output.stems) == 4 and all(s.range_start_s == 5 and s.range_end_s == 35 for s in output.stems)
        assert all("_5000_35000.mp3" in s.url for s in output.stems)
        report["stems_30s"] = result
        report["cpu_or_gpu_under_60s"] = result["enqueue_claim_process_poll_s"] < 60
        write_json(report_path, report)
    if "covering_repeat" not in report:
        result = execute("stems", {**data, "start_s": 10, "end_s": 20}, root)
        assert result["output"] == report["stems_30s"]["output"]
        assert all(10 - stem["range_start_s"] == 5 for stem in result["output"]["stems"])
        report["covering_repeat"] = result
        write_json(report_path, report)
    if "covering_real_precision" not in report:
        # Regression for real-column comparisons after the final range-cache review.
        result = execute("stems", {**data, "start_s": 10.001, "end_s": 20.001}, root)
        assert result["output"] == report["stems_30s"]["output"]
        report["covering_real_precision"] = result
        write_json(report_path, report)
    print(
        json.dumps(
            {
                "report": str(report_path),
                "runtime": report["runtime"],
                "import_id": tid,
                "stem_track": report["stem_track"],
                "timing_s": report["stems_30s"]["enqueue_claim_process_poll_s"],
                "under_60s": report["cpu_or_gpu_under_60s"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback

        print(
            json.dumps(
                {
                    "failure": type(error).__name__,
                    "message": str(error) if isinstance(error, ValueError) else "see frames",
                    "frames": [
                        {"file": Path(f.filename).name, "function": f.name, "line": f.lineno}
                        for f in traceback.extract_tb(error.__traceback__)
                    ],
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
