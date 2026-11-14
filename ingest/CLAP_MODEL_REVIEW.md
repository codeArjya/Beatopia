# CLAP checkpoint decision needed before seed ingest

The implemented shared wrapper preserves the contract default. Do not start a real
embedding corpus with that default: the downloaded music checkpoint fails semantic
acceptance. No library rows have been ingested. Both comparison checkpoints were
loaded with the same installed Transformers 5.23.0 and Torch 2.15.0+cpu, preprocessing,
projection extraction and explicit L2 normalization. No packages were swapped.

## Measured evidence

| Check | `laion/larger_clap_music` | `laion/larger_clap_general` |
| --- | --- | --- |
| Immutable revision | `a0b4534a14f58e20944452dff00a22a06ce629d1` | `ada0c23a36c4e8582805bb38fec3905903f18b41` |
| Mix fixture vs literal `drum loop` cosine | 0.002979 | 0.186066 |
| Drum fixture vs literal `drum loop` cosine | 0.011423 | 0.277668 |
| Mean cosine between four unrelated text prompts | 0.999295 | 0.293701 |
| Finite 512-dimensional unit embeddings | Pass | Pass |
| Drum-fixture acceptance (`> 0.2`) | Fail | Pass |

The text prompts are `a heavy metal guitar solo`, `a slow sad piano ballad`,
`a female opera singer`, and `fast electronic dance music`. The music checkpoint
maps these to almost the same direction. Calling its full forward method directly
reproduces the near-zero audio/text similarity; this is not a feature-output
extraction difference in our wrapper.

The general checkpoint tags the drum fixture with `drum loop`, `808`, and `kick`.
Its mixed-fixture score remains below 0.2: do not claim that comparison passed.
Use the dedicated drum fixture for the drum-specific semantic smoke check and
the mixed fixture for BPM/key/window checks. Both yield 90.666 BPM and three windows;
the mixed fixture gives A minor. Drum-only key estimation spuriously gives F# minor,
so tonal-confidence filtering remains a quality-pass concern.

The model publisher's [discussion #2](https://huggingface.co/laion/larger_clap_music/discussions/2)
reports effectively equal classification scores for unrelated labels. An independent
[reproduction in MTEB #5069](https://github.com/embeddings-benchmark/mteb/issues/5069)
reports near-constant music-checkpoint text features across Transformers versions.
These reports support the local measurements; they do not replace them.

## Recommendation and interim assumption

Use the general checkpoint with the same revision in **ingest, worker and WS2 API**:

```dotenv
CLAP_MODEL=laion/larger_clap_general
CLAP_REVISION=ada0c23a36c4e8582805bb38fec3905903f18b41
```

The existing `CLAP_MODEL` override supports this without schema/API changes.
`CLAP_REVISION` is an optional setting implemented in common to keep deployments
on the same weights. Both models use the same 48 kHz / 512-dimensional contract.
No database dimension change or new library is needed. All processes must restart
after configuration changes because model weights and vocab embeddings are cached.

Meanwhile keep the checked-in default unchanged, leave task 2's acceptance checkbox
open, and do not ingest the seed. The root `.env`, shared documentation and WS2
deployment configuration are outside WS1's allowed edit paths. Human approval and
cross-stream configuration coordination are needed before adopting this recommendation.

If the human prefers to change the shared documented default as well, the proposed
edits for a human-owned `contract:` PR are:

```diff
--- docs/CONTRACT.md (shared helper definition)
-CLAP_MODEL = os.environ.get("CLAP_MODEL", "laion/larger_clap_music")
+CLAP_MODEL = os.environ.get("CLAP_MODEL", "laion/larger_clap_general")
--- docs/CONTRACT.md (environment block), .env.example
-CLAP_MODEL=laion/larger_clap_music
+CLAP_MODEL=laion/larger_clap_general
+CLAP_REVISION=ada0c23a36c4e8582805bb38fec3905903f18b41
```

WS1 can then update its default/revision together after the coordinated decision.
No API model or fixture shape changes are needed. This review is stored inside
`ingest/` because the active task forbids edits to `docs/proposals/`.

## Reproduce on this workspace

From the repository root (cached weights; no network needed):

```powershell
$env:PATH = (Resolve-Path 'common/data/tools/ffmpeg/ffmpeg-9.0.2-essentials_build/bin').Path + ';' + $env:PATH
$env:HF_HUB_CACHE = (Resolve-Path 'common/data/huggingface').Path
$env:HF_HUB_OFFLINE = '1'
$env:OMP_NUM_THREADS = '4'
$env:MKL_NUM_THREADS = '4'
$env:CLAP_MODEL = 'laion/larger_clap_general'
$env:CLAP_REVISION = 'ada0c23a36c4e8582805bb38fec3905903f18b41'
common/.venv/Scripts/python.exe -m common.check_features --fixture web/public/fixtures/audio/drums.wav
```

For the failing baseline, set the music model/revision from the table. For the
mixed-fixture comparison, omit `--fixture`. The command emits actual scores and
returns nonzero when a gate fails. It never writes DB rows or overrides project settings.
