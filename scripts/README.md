# scripts/ (shared tooling)

| Script | Make target | Runs in |
| --- | --- | --- |
| `export_schema.py` (+ `json2ts.mjs`) | `make schema` | api env (+ Node for the TS step) |
| `check_fixtures.py` | `make check-fixtures` | api env |
| `make_fixture_audio.py` | `make fixture-audio` | common env |
| `db_init.py` | `make db-init` | common env |
