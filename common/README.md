# common/ (owner: **WS1**, Audio data & stems)

Python package `common`: the shared helpers from CONTRACT §4 (`clap`, `audio`, `analysis`, `db`, `storage`, `ids`).
WS2 imports `common.clap.embed_text`, `common.db` and `common.storage`; signatures are fixed by the contract.
The package directory is this folder (`common/clap.py`, ...); `ingest`, `worker` and `api` depend on it as an editable
path dependency, so edits here are picked up without reinstalling.

```bash
cd common && uv sync && uv run pytest
```

## torch: CPU by default, CUDA on GPU machines

Every project's `pyproject.toml` pulls `torch` from the PyTorch **CPU** index on Linux/Windows (macOS uses PyPI, which
includes MPS). On a machine with an NVIDIA GPU, swap the wheel in the project you run (`ingest` or `worker`, which both
pull torch in through `common`):

```bash
cd ingest   # or worker
uv sync
uv pip install --reinstall torch --index-url https://download.pytorch.org/whl/cu128   # pick the CUDA tag for your driver
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

`uv sync` puts the CPU build back, so run your scripts with `uv run --no-sync ...` after installing the CUDA build.
For a permanent switch on a GPU box (e.g. the Vultr VM), change the `pytorch-cpu` index URL in that project's
`pyproject.toml` to the CUDA one (don't commit that).
