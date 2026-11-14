"""Validate every shared/fixtures/*.json against shared/schema/api.schema.json (and CONTRACT §3 job outputs).

    uv run --project api python scripts/check_fixtures.py      (or: make check-fixtures)

Also checks that every fixture audio URL (/fixtures/audio/...) exists under web/public/.
"""

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from app.models.api import Stem, TrackDetail

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "shared" / "fixtures"
SCHEMA = ROOT / "shared" / "schema" / "api.schema.json"
PUBLIC = ROOT / "web" / "public"

# CONTRACT §9: fixture file -> response model.
EXPECTED = {
    "chips": "ChipsResponse",
    "search": "SearchResponse",
    "search_empty": "SearchResponse",
    "search_fallback": "SearchResponse",
    "track_detail": "TrackDetail",
    "stems_ready": "StemsResponse",
    "stems_queued": "StemsResponse",
    "job_running": "Job",
    "job_done_stems": "Job",
    "job_done_analyze": "Job",
    "import": "ImportResponse",
    "why": "WhyResponse",
    "assist": "AssistResponse",
}

# CONTRACT §3 job output shapes (Job.output is an untyped dict in the schema).
JOB_OUTPUT = {
    "stems": TypeAdapter(dict[str, list[Stem]]),
    "analyze": TypeAdapter(dict[str, TrackDetail]),
}
JOB_OUTPUT_KEY = {"stems": "stems", "analyze": "track"}


def audio_urls(node: Any) -> list[str]:
    if isinstance(node, dict):
        return [u for v in node.values() for u in audio_urls(v)]
    if isinstance(node, list):
        return [u for v in node for u in audio_urls(v)]
    if isinstance(node, str) and node.startswith("/fixtures/"):
        return [node]
    return []


def main() -> int:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors: list[str] = []
    found = {p.stem for p in FIXTURES.glob("*.json")}
    for missing in sorted(set(EXPECTED) - found):
        errors.append(f"{missing}.json: missing (required by CONTRACT §9)")
    for extra in sorted(found - set(EXPECTED)):
        errors.append(f"{extra}.json: no model mapping in scripts/check_fixtures.py")

    for name, model in EXPECTED.items():
        path = FIXTURES / f"{name}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        validator = Draft202012Validator({"$ref": f"#/$defs/{model}", "$defs": schema["$defs"]})
        for err in validator.iter_errors(data):
            loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
            errors.append(f"{name}.json [{model}] {loc}: {err.message}")
        if model == "Job" and data.get("output") is not None:
            kind = data.get("kind")
            try:
                out = JOB_OUTPUT[kind].validate_python(data["output"])
                if JOB_OUTPUT_KEY[kind] not in out:
                    errors.append(f"{name}.json output: missing key '{JOB_OUTPUT_KEY[kind]}'")
            except (KeyError, ValidationError) as exc:
                errors.append(f"{name}.json output ({kind}): {exc}")
        for url in audio_urls(data):
            if not (PUBLIC / url.lstrip("/")).exists():
                errors.append(f"{name}.json: audio {url} not found in web/public (run make fixture-audio)")

    for e in errors:
        print(f"FAIL {e}")
    print(f"{len(EXPECTED)} fixtures checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
