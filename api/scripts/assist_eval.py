"""T10.3 live eval: the 10 scripted /assist prompts from PLAN §5 against real Gemini (no DB, no CLAP).

    uv run --project api --env-file .env python api/scripts/assist_eval.py [--pause 2]

Each case checks the returned ops (already validated by the chain simulator). Acceptance: >= 9/10 pass.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import gemini as gem  # noqa: E402
from app.core.assist import run_assist  # noqa: E402
from app.core.errors import ApiException  # noqa: E402
from app.core.settings import Settings  # noqa: E402
from app.models.ops import AssistRequest, Op  # noqa: E402

CLIP = {"id": "c1", "source": {"track_id": "jam_1030277", "stem": "mix", "audio_url": "https://x/mix.mp3",
                               "start_s": 15.0, "end_s": 25.667}}  # fmt: skip
SLICED4 = [{"op": "slice", "clip": "c1", "count": 4, "snap": "beat"}]

Check = Callable[[list[dict[str, Any]], str], bool]


def ops_eq(*expected: dict[str, Any]) -> Check:
    def check(ops: list[dict[str, Any]], _: str) -> bool:
        return len(ops) == len(expected) and all(
            all(o.get(k) == v for k, v in e.items()) for o, e in zip(ops, expected, strict=True)
        )

    return check


def fade_after_trim(ops: list[dict[str, Any]], _: str) -> bool:
    return (
        len(ops) == 2
        and ops[0] == {**ops[0], "op": "trim", "clip": "c1", "start_s": 0, "end_s": 2}
        and ops[1]["op"] == "fade_out" and ops[1]["clip"] == "c1" and 0 < ops[1]["ms"] <= 2000
    )  # fmt: skip


def lofi(ops: list[dict[str, Any]], _: str) -> bool:
    filters = [o for o in ops if o["op"] == "filter"]
    return bool(filters) and all(o["type"] == "lowpass" and 500 <= o["freq_hz"] <= 3000 for o in filters) and all(
        o["op"] in ("filter", "gain") for o in ops
    )


def louder_third(ops: list[dict[str, Any]], _: str) -> bool:
    return len(ops) == 1 and ops[0]["op"] == "gain" and ops[0]["clip"] == "c1.3" and ops[0]["db"] > 0


def no_ops(ops: list[dict[str, Any]], reply: str) -> bool:
    return ops == [] and len(reply) > 10


CASES: list[tuple[str, list[dict[str, Any]], Check]] = [
    ("chop this into 4 and reverse the last one", [],
     ops_eq({"op": "slice", "clip": "c1", "count": 4, "snap": "beat"}, {"op": "reverse", "clip": "c1.4"})),
    ("pitch it down 3 semitones like a record", [], ops_eq({"op": "repitch", "clip": "c1", "semitones": -3})),
    ("make it 120 bpm but keep the pitch", [],
     ops_eq({"op": "stretch_to_bpm", "clip": "c1", "target_bpm": 120, "keep_pitch": True})),
    ("slice into 8, then play 1 1 3 2", [],
     ops_eq({"op": "slice", "clip": "c1", "count": 8}, {"op": "arrange", "order": ["c1.1", "c1.1", "c1.3", "c1.2"]})),
    ("just keep the first 2 seconds and fade it out", [], fade_after_trim),
    ("make it sound muffled and lo-fi", [], lofi),
    ("loop it 4 times", [], ops_eq({"op": "loop", "clip": "c1", "times": 4})),
    ("turn up the third piece", SLICED4, louder_third),
    ("reverse c1", SLICED4, no_ops),
    ("add some reverb", [], no_ops),
]  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pause", type=float, default=2.0)
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings.from_env()
    g = gem.from_settings(settings)
    print(f"model {settings.gemini_model}; degraded: {g.degraded_reason()}")
    passed = 0
    for i, (prompt, prior, check) in enumerate(CASES, 1):
        req = AssistRequest.model_validate(
            {"messages": [{"role": "user", "content": prompt}], "editor": {"bpm": 90, "clips": [CLIP], "ops": prior}}
        )
        t = time.perf_counter()
        try:
            resp = run_assist(req, g)
            ops = [Op_dump(o) for o in resp.ops]
            ok, reply = check(ops, resp.reply), resp.reply
        except ApiException as exc:
            ops, ok, reply = [], False, f"<{exc.code}: {exc.message}>"
        ms = (time.perf_counter() - t) * 1000
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} {i:2} {ms:6.0f} ms  {prompt!r}\n        ops {ops}\n        reply {reply!r}")
        time.sleep(args.pause)
    print(f"\n{passed}/{len(CASES)} passed (acceptance: >= 9)")
    return 0 if passed >= 9 else 1


def Op_dump(op: Op) -> dict[str, Any]:  # noqa: N802
    return op.model_dump(exclude_none=True)


if __name__ == "__main__":
    raise SystemExit(main())
