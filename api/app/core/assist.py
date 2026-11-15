"""POST /assist (PLAN §5 P4, T10.3): Gemini function calling over the Op union, validated by the chain simulator.

Manual loop of at most MAX_TURNS model turns. Each op call is validated (`TypeAdapter(Op)` + `ChainSim`) in the
order the model makes it; valid ops are kept, invalid ones go back to the model as `{"ok": false, "error": ...}` so it
can fix the call. The response only ever contains ops that form a valid chain on top of the client's editor state,
and the client appends them as one undo step.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.genai import types
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import TypeAdapter, ValidationError

from app.core import assist_tools, jobs
from app.core.errors import ApiException, bad_request, upstream_error
from app.core.gemini import CallBudget, Gemini, GeminiUnavailable
from app.core.opsim import ChainSim, OpError
from app.core.settings import Settings
from app.core.timing import note, stage
from app.models.api import SearchRequest, StemsRequest
from app.models.ops import AssistRequest, AssistResponse, Op

log = logging.getLogger("app.assist")

MAX_TURNS = 3
MAX_MESSAGES = 20
MAX_REPLY_CHARS = 600
TEMPERATURE = 0.2
THINKING = "LOW"  # MEDIUM was planned; LOW keeps a 2-turn edit under ~5 s on 3.6 Flash
BUDGET = CallBudget(timeout_ms=12_000, attempts=2)
OP_ADAPTER: TypeAdapter[Op] = TypeAdapter(Op)
OP_NAMES = frozenset(assist_tools.op_models())

SYSTEM = """You are the assistant inside a browser sample editor for beginner producers. The user describes an edit
in words; you perform it by calling the edit functions. Every function call you make becomes one step
in a non-destructive edit chain that the user can undo all at once.

How the editor works:
- The editor has clips. Each clip plays a range of a source track. Clip ids are "c1", "c2", ...
- Edits are applied in order, on top of earlier edits. Times in trim and slice are in seconds,
  measured from the clip's current start (0 = the start of the clip as it is now).
- slice cuts a clip into pieces named "<clip>.1", "<clip>.2", ... (numbered from 1, left to right).
  "Chop into 4" means slice with count 4. After a clip is sliced you can no longer edit the parent:
  edit the pieces instead ("the last one" of 4 pieces of c1 is c1.4). Slicing a piece again gives
  "c1.4.1", "c1.4.2", ...
- snap "beat" cuts on the track's beats (the default and usually right), "transient" cuts on hits,
  "none" cuts into equal parts.
- repitch changes pitch AND speed together, like a record ("pitch it down", "slow it down like vinyl",
  "chipmunk"). pitch_shift changes pitch only and keeps the length ("change the key", "tune it").
  Semitones: +12 is one octave up, -12 one octave down.
- stretch_to_bpm sets a new tempo. keep_pitch false (default) also changes pitch, like vinyl;
  use keep_pitch true when the user wants the same pitch.
- loop repeats a clip several times where it appears in the arrangement.
- arrange sets the playback order of clips, repeats allowed ("play 1, 1, 3, 2" means
  ["c1.1","c1.1","c1.3","c1.2"]). Without an arrange step the editor plays all leaf clips in order.
- gain is in dB (a little louder is +3, much quieter is -12). Fades are in milliseconds.
  filter highpass removes lows (try 200-400 Hz to remove bass), lowpass removes highs (try 800-2000 Hz
  for a muffled, "underwater" or lo-fi sound).

Rules:
- Only use clip ids that exist in the current editor state (below) or that your own slice calls in
  this turn create. Clips listed under "sliced" can't be edited; use their pieces.
- If the request is ambiguous about WHICH clip and there is more than one candidate, ask a short
  question instead of guessing. If there is only one clip, use it.
- Use search_library only when the user asks for a different or additional sound; describe what you
  found in one or two sentences (title and why it fits). You cannot add it to the editor yourself:
  tell the user to drag it in from the results.
- Use get_stems only when the user asks to isolate a part (drums, vocals, bass, other).
- If a function returns an error, fix the call once or explain the problem in one sentence.
- After your function calls, reply in at most 2 short sentences: say what you did in plain words and
  suggest one thing to try next. Never invent edits that you did not make with a function call.
- If the user asks for something the editor cannot do (add effects that are not listed, record,
  export), say so briefly and suggest the closest thing it can do.

Current editor state (JSON):
{editor_state_json}

Clips you can edit now: {leaves}
Sliced clips (edit their pieces instead): {sliced}

Track info for the clips (JSON): {track_info_json}
"""


def _track_info(pool: ConnectionPool | None, track_ids: list[str]) -> list[dict[str, Any]]:
    if pool is None or not track_ids:
        return []
    try:
        with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "select id as track_id, title, bpm, key, duration_s from tracks where id = any(%s)", (track_ids,)
            ).fetchall()
    except Exception:  # track info is a hint; never fail the edit over it
        log.warning("assist: track info lookup failed", exc_info=True)
        return []


def system_prompt(req: AssistRequest, sim: ChainSim, info: list[dict[str, Any]]) -> str:
    return SYSTEM.format(
        editor_state_json=req.editor.model_dump_json(),
        leaves=", ".join(sim.leaves()) or "none",
        sliced=", ".join(c for c in sim.order if c in sim.sliced) or "none",
        track_info_json=json.dumps(info, default=str),
    )


class AssistRun:
    """One /assist request: the simulated chain, the accepted ops and the tool handlers."""

    def __init__(self, req: AssistRequest, pool: ConnectionPool | None, settings: Settings | None) -> None:
        self.sim = ChainSim.from_editor(req.editor)
        self.pool = pool
        self.settings = settings
        self.ops: list[Op] = []
        self.rejected = 0
        self.tools_used: list[str] = []

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.tools_used.append(name)
        if name in OP_NAMES:
            return self._op(name, args)
        if name == "search_library":
            return self._search(str(args.get("text", "")))
        if name == "get_stems":
            return self._stems(args)
        return {"ok": False, "error": f"unknown function {name}"}

    def _op(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            op = OP_ADAPTER.validate_python({**args, "op": name})
            trial = self.sim.copy()
            trial.apply(op)
        except ValidationError as exc:
            self.rejected += 1
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"][1:]) or name
            return {"ok": False, "error": f"bad_request: {where}: {first['msg']}"}
        except OpError as exc:
            self.rejected += 1
            return {"ok": False, "error": f"{exc.code}: {exc.message}"}
        self.sim = trial
        self.ops.append(op)
        return {"ok": True, "clips_now": self.sim.leaves()}

    def _search(self, text: str) -> dict[str, Any]:
        if not text.strip() or self.pool is None or self.settings is None:
            return {"error": "search is not available"}
        from app.core.search import run_search  # local import: search imports the planner/CLAP stack

        try:
            # No Gemini here (plan from raw text, score order): keeps the assist turn fast.
            resp = run_search(SearchRequest(text=text, limit=5, session_id="assist"), self.pool, self.settings, None)
        except ApiException as exc:
            return {"error": f"{exc.code}: {exc.message}"}
        return {
            "results": [
                {
                    "title": r.track.title,
                    "artist": r.track.artist,
                    "bars": r.bars,
                    "bpm": r.track.bpm,
                    "key": r.track.key,
                    "tags": r.tags[:5],
                    "why": r.why,
                }
                for r in resp.results
            ]
        }

    def _stems(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.pool is None:
            return {"error": "stems are not available"}
        try:
            req = StemsRequest(start_s=float(args["start_s"]), end_s=float(args["end_s"]))
            with self.pool.connection() as conn:
                resp = jobs.request_stems(conn, str(args["track_id"]), req)
        except (KeyError, TypeError, ValueError, ValidationError):
            return {"error": "bad_request: get_stems needs track_id, start_s and end_s"}
        except ApiException as exc:
            return {"error": f"{exc.code}: {exc.message}"}
        if resp.stems is not None:
            return {"status": "ready", "stems": [s.stem for s in resp.stems]}
        return {"status": "queued", "job_id": resp.job_id, "say": "separating now; open the Stems drawer"}


def summarize(ops: list[Op]) -> str:
    if not ops:
        return 'I couldn\'t make that edit. Try saying which clip and what to change, e.g. "chop c1 into 4".'
    names = ", ".join(dict.fromkeys(op.op.replace("_", " ") for op in ops))
    return f"Done: {names}. Press play to hear it, or undo to go back."


def _contents(req: AssistRequest) -> list[types.Content]:
    msgs = req.messages[-MAX_MESSAGES:]
    return [
        types.Content(role="model" if m.role == "assistant" else "user", parts=[types.Part.from_text(text=m.content)])
        for m in msgs
    ]


def run_assist(
    req: AssistRequest, gemini: Gemini | None, pool: ConnectionPool | None = None, settings: Settings | None = None
) -> AssistResponse:
    if not req.messages or req.messages[-1].role != "user" or not req.messages[-1].content.strip():
        raise bad_request("the last message must be a non-empty user message")
    if not req.editor.clips:
        raise bad_request("the editor has no clips")
    if gemini is None or not gemini.available():
        raise upstream_error("the editing assistant is unavailable right now (Gemini)")

    run = AssistRun(req, pool, settings)
    info = _track_info(pool, sorted({c.source.track_id for c in req.editor.clips}))
    system = system_prompt(req, run.sim, info)
    contents = _contents(req)
    declarations = assist_tools.declarations()
    reply, turns = "", 0
    with stage("assist"):
        while turns < MAX_TURNS:
            turns += 1
            try:
                response = gemini.generate_tools(
                    system=system, contents=contents, declarations=declarations, temperature=TEMPERATURE,
                    thinking=THINKING, budget=BUDGET, what="assist",
                )  # fmt: skip
            except GeminiUnavailable as exc:
                if run.ops:  # keep the edits that already validated
                    break
                raise upstream_error("the editing assistant is unavailable right now (Gemini)") from exc
            calls = response.function_calls or []
            if not calls:
                reply = (response.text or "").strip()
                break
            contents.append(response.candidates[0].content)  # unchanged: carries the thought signatures
            parts = [
                types.Part.from_function_response(
                    name=c.name or "", response=run.call(c.name or "", dict(c.args or {}))
                )
                for c in calls
            ]
            contents.append(types.Content(role="user", parts=parts))
    note(assist_turns=turns, assist_ops=len(run.ops), assist_rejected=run.rejected, assist_tools=run.tools_used)
    if not reply:
        reply = summarize(run.ops)
    return AssistResponse(reply=reply[:MAX_REPLY_CHARS], ops=run.ops)
