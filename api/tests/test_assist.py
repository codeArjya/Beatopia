"""T10.1–T10.3: tool registry, chain simulator and the /assist function-calling loop (Gemini faked)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from google.genai import errors, types

from app import main
from app.core import assist, assist_tools
from app.core import gemini as gem
from app.core.opsim import ChainSim, OpError
from app.core.settings import Settings
from app.fixture_routes import fixture
from app.models.ops import AssistRequest, AssistResponse, EditorState, Reverse, Slice

# ---- tool registry ----


def test_registry_has_every_op_and_flat_schemas() -> None:
    schemas = assist_tools.tool_schemas()
    assert list(schemas) == [
        "trim", "slice", "reverse", "repitch", "pitch_shift", "stretch_to_bpm", "gain", "fade_in", "fade_out",
        "normalize", "loop", "filter", "arrange", "search_library", "get_stems",
    ]  # fmt: skip
    assert set(assist_tools.DESCRIPTIONS) == set(schemas)
    for name, s in schemas.items():
        assert s["type"] == "object" and "op" not in s["properties"], name
        flat = repr(s)
        assert "anyOf" not in flat and "'title'" not in flat and "'null'" not in flat, name
    assert schemas["slice"]["required"] == ["clip"]
    assert schemas["slice"]["properties"]["count"] == {"maximum": 32, "minimum": 2, "type": "integer"}
    assert schemas["filter"]["required"] == ["clip", "type", "freq_hz"]
    assert schemas["stretch_to_bpm"]["properties"]["keep_pitch"]["description"] == "Default false."
    assert schemas["arrange"]["properties"]["order"]["minItems"] == 1
    assert len(assist_tools.declarations()) == 15


# ---- chain simulator ----


def editor(**over: Any) -> EditorState:
    base = AssistRequest.model_validate(fixture_request()).editor.model_dump()
    return EditorState.model_validate({**base, **over})


def fixture_request() -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": "chop this into 4 and reverse the last one"}],
        "editor": {
            "bpm": 90,
            "clips": [
                {"id": "c1", "source": {"track_id": "jam_1", "stem": "mix", "audio_url": "https://x/a.mp3",
                                        "start_s": 15.0, "end_s": 25.667}},
            ],
            "ops": [],
        },
    }  # fmt: skip


def test_sim_slice_children_and_sliced_parent() -> None:
    sim = ChainSim.from_editor(editor())
    sim.apply(Slice(op="slice", clip="c1", count=4))
    assert sim.leaves() == ["c1.1", "c1.2", "c1.3", "c1.4"]
    sim.apply(Reverse(op="reverse", clip="c1.4"))
    with pytest.raises(OpError) as exc:
        sim.apply(Reverse(op="reverse", clip="c1"))
    assert exc.value.code == "clip_is_sliced" and "c1.1" in exc.value.message
    with pytest.raises(OpError) as exc:
        sim.apply(Reverse(op="reverse", clip="c1.5"))
    assert exc.value.code == "bad_request"
    sim.apply(Slice(op="slice", clip="c1.2", at=[0.5, 1.0]))
    assert sim.leaves() == ["c1.1", "c1.3", "c1.4", "c1.2.1", "c1.2.2", "c1.2.3"]


@pytest.mark.parametrize(
    "op",
    [
        {"op": "slice", "clip": "c1"},
        {"op": "slice", "clip": "c1", "count": 4, "at": [1.0]},
        {"op": "slice", "clip": "c1", "at": [2.0, 1.0]},
        {"op": "trim", "clip": "c1", "start_s": 3, "end_s": 2},
        {"op": "arrange", "order": []},
        {"op": "arrange", "order": ["c9"]},
    ],
)
def test_sim_rejects_bad_ops(op: dict[str, Any]) -> None:
    sim = ChainSim.from_editor(editor())
    with pytest.raises(OpError):
        sim.apply(assist.OP_ADAPTER.validate_python(op))


def test_sim_replays_existing_editor_ops() -> None:
    sim = ChainSim.from_editor(editor(ops=[{"op": "slice", "clip": "c1", "count": 4, "snap": "beat"}]))
    assert sim.leaves() == ["c1.1", "c1.2", "c1.3", "c1.4"] and "c1" in sim.sliced


# ---- the loop, with a fake Gemini ----


def call(name: str, **args: Any) -> types.Part:
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def reply(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))]
    )


def text(t: str) -> types.GenerateContentResponse:
    return reply(types.Part.from_text(text=t))


class FakeModels:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.seen: list[list[types.Content]] = []
        self.configs: list[types.GenerateContentConfig] = []

    def generate_content(self, *, model: str, contents: list[types.Content], config: Any) -> Any:
        self.seen.append(list(contents))
        self.configs.append(config)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeClient:
    def __init__(self, *replies: Any) -> None:
        self.models = FakeModels(list(replies))


def run(*replies: Any, req: dict[str, Any] | None = None) -> tuple[AssistResponse, FakeModels]:
    client = FakeClient(*replies)
    g = gem.Gemini(client, "gemini-3.6-flash")
    resp = assist.run_assist(AssistRequest.model_validate(req or fixture_request()), g)
    return resp, client.models


def test_chop_and_reverse_matches_the_fixture() -> None:
    resp, models = run(
        reply(call("slice", clip="c1", count=4, snap="beat"), call("reverse", clip="c1.4")),
        text(fixture("assist")["reply"]),
    )
    assert resp == AssistResponse.model_validate(fixture("assist"))
    # turn 2 history: user msg, model turn (unchanged), function responses
    second = models.seen[1]
    assert [c.role for c in second] == ["user", "model", "user"]
    responses = [p.function_response for p in second[2].parts or []]
    assert [r.response for r in responses if r] == [
        {"ok": True, "clips_now": ["c1.1", "c1.2", "c1.3", "c1.4"]},
        {"ok": True, "clips_now": ["c1.1", "c1.2", "c1.3", "c1.4"]},
    ]
    cfg = models.configs[0]
    assert cfg.automatic_function_calling.disable is True
    assert cfg.tool_config.function_calling_config.mode == "AUTO"
    assert "Clips you can edit now: c1" in cfg.system_instruction


def test_invalid_op_is_sent_back_and_repaired() -> None:
    resp, models = run(
        reply(call("slice", clip="c1", count=4), call("reverse", clip="c1")),  # parent is sliced
        reply(call("reverse", clip="c1.4")),
        text("Sliced into 4 and reversed the last piece."),
    )
    assert [o.model_dump(exclude_defaults=True) for o in resp.ops] == [
        {"op": "slice", "clip": "c1", "count": 4},
        {"op": "reverse", "clip": "c1.4"},
    ]
    err = models.seen[1][2].parts[1].function_response.response  # type: ignore[index,union-attr]
    assert err["ok"] is False and err["error"].startswith("clip_is_sliced")


def test_schema_violation_is_rejected_not_returned() -> None:
    resp, models = run(reply(call("gain", clip="c1", db=40)), text("That is too loud for the editor."))
    assert resp.ops == [] and resp.reply == "That is too loud for the editor."
    err = models.seen[1][2].parts[0].function_response.response  # type: ignore[index,union-attr]
    assert err["ok"] is False and "db" in err["error"]


def test_no_tool_call_reply_only() -> None:
    resp, _ = run(text("Reverb isn't available; try a lowpass filter for a softer, distant sound."))
    assert resp.ops == [] and "lowpass" in resp.reply


def test_turn_limit_keeps_valid_ops_and_summarizes() -> None:
    resp, models = run(
        reply(call("slice", clip="c1", count=2)),
        reply(call("reverse", clip="c1.1")),
        reply(call("gain", clip="c1.2", db=3)),
    )
    assert [o.op for o in resp.ops] == ["slice", "reverse", "gain"] and len(models.seen) == 3
    assert resp.reply.startswith("Done: slice, reverse, gain")


def test_gemini_failure() -> None:
    boom = errors.APIError(503, {"error": {"code": 503, "message": "busy", "status": "UNAVAILABLE"}})
    with pytest.raises(Exception) as exc:
        run(boom)
    assert getattr(exc.value, "code", None) == "upstream_error"
    # a failure after valid ops keeps them
    resp, _ = run(reply(call("reverse", clip="c1")), boom)
    assert [o.op for o in resp.ops] == ["reverse"]


def test_route_errors() -> None:
    app = main.create_app(Settings.from_env({"SUPABASE_URL": "https://ref.supabase.co", "GEMINI_DEGRADED": "1"}))
    app.state.gemini = gem.from_settings(app.state.settings)
    app.state.pool = None
    c = TestClient(app)
    r = c.post("/assist", json=fixture_request())
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_error"
    bad = {**fixture_request(), "messages": [{"role": "assistant", "content": "hi"}]}
    assert c.post("/assist", json=bad).json()["error"]["code"] == "bad_request"
