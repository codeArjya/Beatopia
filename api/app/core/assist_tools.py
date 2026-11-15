"""/assist tool registry (PLAN §5 P4): one function per Op model + search_library + get_stems.

Parameter schemas are generated from the contract Op models (so they can't drift): `op` and titles are stripped,
`anyOf [X, null]` becomes an optional X, and defaults move into the description (Gemini schemas stay flat).
"""

from __future__ import annotations

import json
from typing import Any, get_args

from google.genai import types
from pydantic import BaseModel

from app.models.ops import Op

DESCRIPTIONS: dict[str, str] = {
    "trim": "Keep only part of a clip. start_s and end_s are seconds from the clip's current start.",
    "slice": (
        "Chop a clip into pieces named <clip>.1 .. <clip>.n (left to right). Give count (number of pieces) OR at "
        "(cut times in seconds from the clip start), not both. snap: beat (default, cuts on beats), transient "
        "(cuts on hits) or none (equal parts). After slicing, edit the pieces, not the parent."
    ),
    "reverse": "Play a clip backwards.",
    "repitch": "Change pitch and speed together, like a record. Positive semitones = higher and faster.",
    "pitch_shift": "Change pitch only and keep the length. +12 = one octave up.",
    "stretch_to_bpm": (
        "Change a clip's tempo to target_bpm. keep_pitch false (default) also changes pitch like vinyl; "
        "keep_pitch true keeps the pitch."
    ),
    "gain": "Make a clip louder (positive dB) or quieter (negative dB). +3 is a little louder, -12 much quieter.",
    "fade_in": "Fade a clip in over ms milliseconds.",
    "fade_out": "Fade a clip out over ms milliseconds.",
    "normalize": "Set a clip's peak level in dB (default -1).",
    "loop": "Repeat a clip `times` times wherever it plays in the arrangement.",
    "filter": (
        "highpass removes lows below freq_hz (200-400 Hz removes bass); lowpass removes highs above freq_hz "
        "(800-2000 Hz sounds muffled or lo-fi)."
    ),
    "arrange": 'Set the playback order of clips, repeats allowed, e.g. ["c1.1", "c1.1", "c1.3"].',
    "search_library": (
        "Search the sample library for a different or additional sound. Returns up to 5 matches "
        "(title, artist, bars, bpm, key, why). You cannot add them to the editor."
    ),
    "get_stems": (
        "Isolate the parts (vocals, drums, bass, other) of a source range of a track (at most 60 s). Returns the "
        "stems if they exist, or starts a separation job."
    ),
}

EXTRA_TOOLS: dict[str, dict[str, Any]] = {
    "search_library": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "What the sound should be like."}},
        "required": ["text"],
    },
    "get_stems": {
        "type": "object",
        "properties": {
            "track_id": {"type": "string"},
            "start_s": {"type": "number", "minimum": 0},
            "end_s": {"type": "number", "minimum": 0},
        },
        "required": ["track_id", "start_s", "end_s"],
    },
}


def op_models() -> dict[str, type[BaseModel]]:
    union = get_args(Op)[0]
    return {m.model_fields["op"].annotation.__args__[0]: m for m in get_args(union)}  # type: ignore[union-attr]


def _clean(prop: dict[str, Any]) -> dict[str, Any]:
    prop = {k: v for k, v in prop.items() if k != "title"}
    if "anyOf" in prop:
        options = [o for o in prop.pop("anyOf") if o.get("type") != "null"]
        if len(options) == 1:
            prop = {**options[0], **prop}
    default = prop.pop("default", None)
    if "items" in prop:
        prop["items"] = _clean(prop["items"])
    if default is not None:
        prop["description"] = (prop.get("description", "") + f" Default {json.dumps(default)}.").strip()
    return {k: v for k, v in prop.items() if k != "title"}


def op_parameters(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    props = {name: _clean(p) for name, p in schema["properties"].items() if name != "op"}
    required = [r for r in schema.get("required", []) if r != "op"]
    if model.__name__ == "Arrange":
        props["order"]["minItems"] = 1
    return {"type": "object", "properties": props, "required": required}


def tool_schemas() -> dict[str, dict[str, Any]]:
    """name → parameters JSON schema, op functions first (in Op union order), then the two helpers."""
    return {**{name: op_parameters(m) for name, m in op_models().items()}, **EXTRA_TOOLS}


def declarations() -> list[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(name=name, description=DESCRIPTIONS[name], parameters_json_schema=schema)
        for name, schema in tool_schemas().items()
    ]
