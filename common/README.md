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

## Audio and service preflight

FFmpeg with `libmp3lame` must be on PATH. Helpers decode local files or HTTP(S)
audio to float32 mono (channel average), and atomically publish 44.1 kHz stereo
MP3s at 192 kbps. A failed transcode preserves an existing destination.

Run from the repository root:

```bash
uv run --no-sync --project common python -m common.preflight
uv run --no-sync --project common --env-file .env python -m common.preflight --live
uv run --no-sync --project common pytest common/tests
```

The live check performs a 512-dimensional pgvector roundtrip and reads table
counts. It uploads the same synthetic MP3 twice to a unique test path, verifies
public bytes and decoding, then removes that object. It does not insert library
tracks or apply migrations. Output includes package versions and safe error types,
never credentials. The public `audio` bucket and contract migrations must exist.

This Windows workspace has a checksum-verified FFmpeg 9.0.2 build in ignored
`common/data/tools/ffmpeg/ffmpeg-9.0.2-essentials_build/bin`. For this shell only:

```powershell
$env:PATH = (Resolve-Path 'common/data/tools/ffmpeg/ffmpeg-9.0.2-essentials_build/bin').Path + ';' + $env:PATH
```

`connect()` registers pgvector on each connection and returns it outside a
transaction. Callers own its lifetime and transaction scope (`with connect()`).
With locked pgvector 0.5.1, selected vectors are `Vector` objects; use
`.to_numpy()` when array operations are needed. Inserts accept NumPy arrays.

## CLAP and analysis acceptance

`common.clap` lazily loads the same checkpoint for audio/text, pins the default
model revision, resamples audio only here to 48 kHz and returns normalized float32
512-dimensional vectors. It processes batches of 16, retries smaller batches on
OOM, then falls back to CPU if a single accelerator input still fails. Empty
batches do not load weights. Windows longer than 10 seconds are deterministically
cropped to their first 10 seconds; short windows are zero-padded only inside the
feature extractor. Model loading/inference is serialized across callers.

`CLAP_MODEL` and optional `CLAP_REVISION` must match in ingest, worker and API.
`HF_HUB_CACHE` can point at the downloaded cache; `HF_HUB_OFFLINE=1` uses it offline.
Restart processes after changing model settings. Keep `ingest/vocab.txt` available
alongside common: tagging reads its category headers and caches text embeddings.

```bash
uv run --no-sync --project common python -m common.check_features
uv run --no-sync --project common python -m common.check_features --fixture web/public/fixtures/audio/drums.wav
```

These real-model checks are separate from offline unit tests and intentionally
fail for the current contract-default checkpoint. See
[`ingest/CLAP_MODEL_REVIEW.md`](../ingest/CLAP_MODEL_REVIEW.md) for measured evidence
and the tested alternative awaiting cross-stream approval. Do not seed a corpus
until the model check passes with the agreed configuration.

Analysis returns seconds on the supplied audio timeline, linear RMS, bounded
loopability/density, and null tempo for low-confidence beats. Long-song pieces
must be analyzed/windowed separately by ingest to avoid windows crossing joins.
