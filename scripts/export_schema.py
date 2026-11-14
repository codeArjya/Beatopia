"""Pydantic contract models -> shared/schema/api.schema.json -> web/lib/types/api.ts.

    uv run --project api python scripts/export_schema.py      (or: make schema)

The TS step needs Node + pnpm with web/ installed (json-schema-to-typescript). Without them the JSON schema is still
written and the TS step is skipped with a warning; run `make schema` on a machine with Node before committing.
"""

import inspect
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel, create_model

from app.models import api, ops

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "shared" / "schema" / "api.schema.json"
TS_PATH = ROOT / "web" / "lib" / "types" / "api.ts"

# Named aliases json-schema-to-typescript can't infer from inline enums (appended to api.ts).
TS_FOOTER = """export type StemName = Result["stem"];
export type Source = TrackLite["source"];
export type OpName = Op["op"];
"""


def contract_models() -> dict[str, type[BaseModel]]:
    models: dict[str, type[BaseModel]] = {}
    for module in (api, ops):
        for name, obj in vars(module).items():
            if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
                if obj.__module__ == module.__name__:
                    models[name] = obj
    return models


def build_schema() -> dict:
    models = contract_models()
    fields = {name: (model, ...) for name, model in models.items()}
    fields["Op"] = (ops.Op, ...)
    root = create_model("ApiSchema", **fields)  # type: ignore[call-overload]
    schema = root.model_json_schema(ref_template="#/$defs/{model}")
    schema["description"] = "Beatopia API contract (CONTRACT §5). Generated; do not edit."
    # Expose the Op union as a named definition so fixtures and clients can reference it.
    schema["$defs"]["Op"] = schema["properties"]["Op"]
    schema["properties"]["Op"] = {"$ref": "#/$defs/Op"}
    return schema


def write_ts() -> None:
    node = shutil.which("node")
    if not node or not (ROOT / "web" / "node_modules" / "json-schema-to-typescript").exists():
        print("WARNING: node or web/node_modules missing; skipped web/lib/types/api.ts (run `make schema` with Node).")
        return
    TS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        footer = Path(tmp) / "footer.ts"
        footer.write_text(TS_FOOTER, encoding="utf-8")
        script = ROOT / "scripts" / "json2ts.mjs"
        subprocess.run([node, str(script), str(SCHEMA_PATH), str(TS_PATH), str(footer)], check=True)
    print(f"wrote {TS_PATH.relative_to(ROOT)}")


def main() -> None:
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(json.dumps(build_schema(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {SCHEMA_PATH.relative_to(ROOT)}")
    write_ts()


if __name__ == "__main__":
    sys.exit(main())
