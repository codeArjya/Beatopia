# CONTRACT.md: the shared interface for all four streams

This file is the source of truth that WS1–WS4 build against. Code in `api/app/models/` must match it exactly.
To change anything here: write `docs/proposals/<stream>-<topic>.md`, get the owners of every affected stream to agree, then land a
`contract: ...` PR that updates this file, the models, the generated schema and the fixtures **together**.

---

## 1. Repo layout and ownership

```text
sample-app/
├─ AGENTS.md, CLAUDE.md            # shared (contract)
├─ docs/                           # shared: CONTRACT.md, SETUP.md, handoff/, proposals/
├─ shared/schema/                  # generated, never hand-edited
├─ shared/fixtures/                # shared (contract): JSON responses for every endpoint
├─ db/migrations/                  # WS1
├─ common/                         # WS1: Python package `common` (db, storage, clap, audio, analysis, ids)
├─ ingest/                         # WS1
├─ worker/                         # WS1: polls `jobs`, runs stems + import analysis
├─ api/                            # WS2: FastAPI app (api/app/models = contract)
├─ deploy/                         # WS2: Dockerfiles, docker-compose.yml, Caddyfile
├─ web/
│  ├─ app/ (except app/editor/)    # WS3
│  ├─ app/editor/                  # WS4
│  ├─ components/ui/               # shadcn generated (WS3 adds components)
│  ├─ components/adapters/         # WS3
│  ├─ components/search/           # WS3 (includes StemsDrawer, ImportDropzone)
│  ├─ components/editor/           # WS4 (includes ChatPanel)
│  ├─ lib/api/                     # WS3 (typed client + TanStack hooks for EVERY endpoint)
│  ├─ lib/audio/                   # WS4
│  ├─ lib/types/                   # generated from shared/schema
│  └─ stores/                      # WS4
└─ Makefile                        # shared
```

**Lockfiles and dependency manifests** (`web/package.json`, `*/pyproject.toml`): the bootstrap installs
everything known up front. If you add a dependency, mention it in your PR title (`[dep]`). On rebase
conflicts, take `main`'s lockfile and re-run `pnpm install` / `uv sync`.

---

## 2. IDs and storage paths

| Thing | Format | Example |
| --- | --- | --- |
| Track id | `{source}_{source_id}` | `fs_482913`, `jam_1532881`, `fma_000123`, `imp_3f9a1c2e` |
| Window id | `{track_id}:{stem}:{start_ms}`; **opaque to clients**: always read `start_s`/`end_s`, never parse the id | `fs_482913:mix:15000` |
| Job id | UUID | |
| Session id | random UUID from the browser (localStorage `session_id`) | |

Supabase Storage, one **public** bucket `audio`:

| Object | Path |
| --- | --- |
| Library track audio (browser playback, 44.1 kHz stereo MP3 192k) | `tracks/{track_id}/mix.mp3` |
| Pre-separated stem (hero tracks, full length) | `tracks/{track_id}/stems/{stem}.mp3` |
| On-demand stem for a range | `tracks/{track_id}/stems/{stem}_{start_ms}_{end_ms}.mp3` |
| Desktop import original | `imports/{track_id}/original.{ext}` and normalized `imports/{track_id}/mix.mp3` |

Public URL = `{SUPABASE_URL}/storage/v1/object/public/audio/{path}`. `common.storage.public_url(path)` builds it.

---

## 3. Database (Postgres + pgvector), `db/migrations/001_init.sql`

```sql
create extension if not exists vector;

create table tracks (
  id text primary key,
  source text not null check (source in ('freesound','jamendo','fma','ccmixter','archive','import')),
  source_id text,
  source_url text,
  title text not null,
  artist text,
  license text not null,            -- e.g. 'CC0', 'CC-BY-4.0', 'CC-BY-SA-3.0', 'CC-BY-NC-4.0'
  attribution text not null default '',
  duration_s real not null,
  bpm real,
  key text,                          -- e.g. 'A minor', 'F# major'
  beat_times real[] not null default '{}',
  audio_path text not null,          -- storage path of mix.mp3
  is_hero boolean not null default false,
  created_at timestamptz not null default now()
);

create table windows (
  id text primary key,
  track_id text not null references tracks(id) on delete cascade,
  stem text not null default 'mix',  -- mix|vocals|drums|bass|other|guitar|piano
  start_s real not null,
  end_s real not null,
  embedding vector(512) not null,    -- L2-normalized CLAP audio embedding
  tags text[] not null default '{}',
  tag_scores jsonb not null default '{}',
  loopability real not null default 0,   -- 0..1, higher = more regular onsets across bars
  rms real not null default 0,
  density real not null default 0.5      -- 0..1, lower = sparser (fewer things playing)
);
create index windows_track_idx on windows(track_id);
create index windows_tags_idx on windows using gin(tags);

create table stems (
  track_id text not null references tracks(id) on delete cascade,
  stem text not null,
  range_start_s real not null default 0,
  range_end_s real not null,
  path text not null,
  model text not null,
  primary key (track_id, stem, range_start_s, range_end_s)
);

create table notes (
  window_id text primary key references windows(id) on delete cascade,
  text text not null,
  model text not null,
  created_at timestamptz not null default now()
);

create table jobs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('stems','analyze')),
  status text not null default 'queued' check (status in ('queued','running','done','error')),
  progress real not null default 0,
  input jsonb not null,
  output jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index jobs_queue_idx on jobs(status, created_at);

create table events (
  id bigserial primary key,
  session_id text not null,
  query_id text,
  window_id text,
  action text not null check (action in ('play','pick','export','skip')),
  created_at timestamptz not null default now()
);

create table plan_cache (
  hash text primary key,
  plan jsonb not null,
  created_at timestamptz not null default now()
);
```

Job `input` shapes:
- `stems`: `{"track_id": str, "start_s": float, "end_s": float, "model": "htdemucs"|"htdemucs_6s"}`
- `analyze`: `{"track_id": str, "path": str}` (storage path of the uploaded original)

Job `output` shapes: `stems` → `StemsJobOutput` `{"stems": [Stem, ...]}`; `analyze` → `AnalyzeJobOutput`
`{"track": TrackDetail}` (models in §5; `GET /jobs/{id}` validates them).

The worker claims jobs with `select ... for update skip locked` and updates `progress` (0..1).

---

## 4. Shared Python helpers (`common/`, owned by WS1, consumed by WS2)

Signatures are fixed. Bodies are WS1's job; the bootstrap writes stubs that raise `NotImplementedError`.

```python
# common/clap.py: the SAME model at ingest and at query time
CLAP_MODEL = os.environ.get("CLAP_MODEL", "laion/larger_clap_music")   # set laion/larger_clap_general (§8)
CLAP_REVISION = os.environ.get("CLAP_REVISION", ...)                   # pinned commit; must match the ingest
def embed_audio(chunks: list[np.ndarray], sr: int) -> np.ndarray: ...   # (n, 512), L2-normalized; resamples to 48 kHz
def embed_text(texts: list[str]) -> np.ndarray: ...                   # (n, 512), L2-normalized

# common/audio.py
def load_mono(path_or_url: str, sr: int = 44100) -> tuple[np.ndarray, int]: ...
def to_mp3(src_path: str, dst_path: str, bitrate: str = "192k") -> None: ...   # ffmpeg

# common/analysis.py: used by ingest AND by the worker's 'analyze' job
@dataclass
class WindowFeatures: start_s: float; end_s: float; loopability: float; rms: float; density: float
@dataclass
class TrackFeatures: duration_s: float; bpm: float | None; key: str | None; beat_times: list[float]
def analyze_track(y: np.ndarray, sr: int) -> TrackFeatures: ...
def make_windows(y: np.ndarray, sr: int, feats: TrackFeatures, length_s=10.0, hop_s=5.0) -> list[WindowFeatures]: ...
def zero_shot_tags(embeddings: np.ndarray) -> list[tuple[list[str], dict[str, float]]]: ...  # uses ingest/vocab.txt

# common/db.py: psycopg 3 + pgvector, DATABASE_URL
def connect() -> psycopg.Connection: ...
# common/storage.py: supabase-py with the service role key
def upload(local_path: str, path: str, content_type: str) -> str: ...   # returns public URL
def public_url(path: str) -> str: ...
# common/ids.py
def window_id(track_id: str, stem: str, start_s: float) -> str: ...
```

---

## 5. API models (`api/app/models/api.py` and `ops.py`, Pydantic v2)

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

StemName = Literal["mix", "vocals", "drums", "bass", "other", "guitar", "piano"]
Source = Literal["freesound", "jamendo", "fma", "ccmixter", "archive", "import"]

class ApiError(BaseModel):
    code: str
    message: str            # every non-2xx response body is {"error": ApiError}

# ---- chips ----
class ChipFilter(BaseModel):
    tags: list[str] = []
    bpm_range: tuple[float, float] | None = None
    key: str | None = None

class Chip(BaseModel):
    id: str                  # e.g. "inst.trumpet", "genre.soul", "mood.melancholy", "tempo.90", "key.a_minor"
    label: str
    category: Literal["instrument", "genre", "mood", "tempo", "key"]
    filter: ChipFilter

class ChipCategory(BaseModel):
    id: Literal["instrument", "genre", "mood", "tempo", "key"]
    label: str
    color: str               # CSS variable name, e.g. "--chip-instrument"
    chips: list[Chip]

class ChipsResponse(BaseModel):
    categories: list[ChipCategory]

# ---- search ----
class SearchPlan(BaseModel):
    clap_text: str
    must_tags: list[str] = []
    exclude_tags: list[str] = []
    bpm_range: tuple[float, float] | None = None
    key: str | None = None
    stems_wanted: list[StemName] = []
    prefer_sparse: bool = False          # "find a cleaner moment": favor low-density windows

class SearchRequest(BaseModel):
    text: str | None = None
    chips: list[str] = []                # chip ids, order = stacking order
    limit: int = Field(8, ge=1, le=24)
    session_id: str

class TrackLite(BaseModel):
    id: str
    title: str
    artist: str | None = None
    source: Source
    source_url: str | None = None
    license: str
    attribution: str
    duration_s: float
    bpm: float | None = None
    key: str | None = None
    is_hero: bool = False

class Result(BaseModel):
    window_id: str
    track: TrackLite
    stem: StemName
    audio_url: str           # mix.mp3 or the stem file; play from start_s to end_s
    start_s: float
    end_s: float
    bars: Literal[1, 2, 4, 8, 16]
    tags: list[str]
    score: float             # 0..1
    why: str | None = None   # null = not cached yet; client may call POST /why

class SearchResponse(BaseModel):
    query_id: str
    plan: SearchPlan
    results: list[Result]
    fallback_used: bool = False

# ---- tracks / stems / jobs / imports ----
class Window(BaseModel):
    id: str
    track_id: str
    stem: StemName
    start_s: float
    end_s: float
    tags: list[str]
    loopability: float
    rms: float
    density: float

class Stem(BaseModel):
    track_id: str
    stem: StemName
    url: str
    range_start_s: float
    range_end_s: float
    model: str

class TrackDetail(BaseModel):
    track: TrackLite
    audio_url: str
    beat_times: list[float]
    windows: list[Window]
    stems: list[Stem]

class StemsRequest(BaseModel):
    start_s: float
    end_s: float             # server rejects ranges > 60 s with code "range_too_long"
    model: Literal["htdemucs", "htdemucs_6s"] = "htdemucs"

class StemsResponse(BaseModel):
    job_id: str | None = None        # set when separation was queued
    stems: list[Stem] | None = None  # set when stems covering the range already exist

class StemsJobOutput(BaseModel):
    stems: list[Stem]

class AnalyzeJobOutput(BaseModel):
    track: TrackDetail

class Job(BaseModel):
    id: str
    kind: Literal["stems", "analyze"]
    status: Literal["queued", "running", "done", "error"]
    progress: float
    output: StemsJobOutput | AnalyzeJobOutput | None = None   # stems job → StemsJobOutput, analyze → AnalyzeJobOutput
    error: str | None = None

class ImportResponse(BaseModel):
    track_id: str
    job_id: str                      # kind "analyze"; poll GET /jobs/{id}

class WhyRequest(BaseModel):
    window_id: str

class WhyResponse(BaseModel):
    window_id: str
    note: str

class EventRequest(BaseModel):
    session_id: str
    query_id: str | None = None
    window_id: str
    action: Literal["play", "pick", "export", "skip"]
```

```python
# api/app/models/ops.py: the editor's operation chain, also Gemini's tool registry
class ClipSource(BaseModel):
    track_id: str
    stem: StemName = "mix"
    audio_url: str
    start_s: float
    end_s: float

class Clip(BaseModel):
    id: str                  # "c1", "c2"...; slice children are "c1.1", "c1.2", ...
    source: ClipSource

class Trim(BaseModel):          op: Literal["trim"]; clip: str; start_s: float; end_s: float      # relative to clip
class Slice(BaseModel):         op: Literal["slice"]; clip: str; count: int | None = Field(None, ge=2, le=32); at: list[float] | None = None; snap: Literal["beat", "transient", "none"] = "beat"
class Reverse(BaseModel):       op: Literal["reverse"]; clip: str
class Repitch(BaseModel):       op: Literal["repitch"]; clip: str; semitones: float = Field(ge=-24, le=24)
class PitchShift(BaseModel):    op: Literal["pitch_shift"]; clip: str; semitones: float = Field(ge=-24, le=24)
class StretchToBpm(BaseModel):  op: Literal["stretch_to_bpm"]; clip: str; target_bpm: float = Field(ge=40, le=240); keep_pitch: bool = False
class Gain(BaseModel):          op: Literal["gain"]; clip: str; db: float = Field(ge=-36, le=12)
class FadeIn(BaseModel):        op: Literal["fade_in"]; clip: str; ms: float = Field(ge=0, le=10000)
class FadeOut(BaseModel):       op: Literal["fade_out"]; clip: str; ms: float = Field(ge=0, le=10000)
class Normalize(BaseModel):     op: Literal["normalize"]; clip: str; peak_db: float = -1.0
class Loop(BaseModel):          op: Literal["loop"]; clip: str; times: int = Field(ge=1, le=16)
class Filter(BaseModel):        op: Literal["filter"]; clip: str; type: Literal["highpass", "lowpass"]; freq_hz: float = Field(ge=20, le=20000)
class Arrange(BaseModel):       op: Literal["arrange"]; order: list[str]   # clip ids, repeats allowed

Op = Annotated[Union[Trim, Slice, Reverse, Repitch, PitchShift, StretchToBpm, Gain, FadeIn, FadeOut,
                     Normalize, Loop, Filter, Arrange], Field(discriminator="op")]

class EditorState(BaseModel):
    bpm: float | None = None
    clips: list[Clip]
    ops: list[Op]
    arrangement: list[str] = []      # empty = all leaf clips in creation order

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class AssistRequest(BaseModel):
    messages: list[ChatMessage]
    editor: EditorState

class AssistResponse(BaseModel):
    reply: str
    ops: list[Op]                    # validated server-side; client appends them as one undo step
```

### Op chain semantics (fixed; both WS2 and WS4 rely on this)

1. **Non-destructive replay.** Sources are never modified. A clip's audio = its source range, then every op that
   targets it, in list order. Undo = drop ops from the end.
2. **Slice creates children** `{clip}.1 … {clip}.n` (1-based) from the clip's buffer *at that point in the chain*.
   After a clip has been sliced, ops targeting the parent are invalid (`code: "clip_is_sliced"`).
3. `trim`, `slice.at` times are seconds **relative to the clip's current start**.
4. `snap: "beat"` uses `TrackDetail.beat_times`; `"transient"` uses client-side onset detection; `"none"` = equal parts.
5. `repitch` changes length (rate = 2^(st/12)). `pitch_shift` keeps length (Tone granular). `stretch_to_bpm`
   uses the track's bpm; `keep_pitch=false` → repitch by tempo ratio.
6. `loop` repeats the clip `times` times wherever it appears in the arrangement.
7. `arrange` replaces the arrangement. Rendering concatenates arrangement clips with no gaps.
8. Export = 44.1 kHz, 16-bit PCM WAV, stereo if any source is stereo.

---

## 6. Endpoints

Base URL `NEXT_PUBLIC_API_URL`. JSON everywhere except `/imports` (multipart). CORS allows the web origin.

| Method + path | Body | 200 response | Notes |
| --- | --- | --- | --- |
| `GET /health` | — | `{"ok": true}` | |
| `GET /chips` | — | `ChipsResponse` | built from `ingest/vocab.txt` + fixed tempo/key chips |
| `POST /search` | `SearchRequest` | `SearchResponse` | target < 3 s p50 |
| `GET /tracks/{id}` | — | `TrackDetail` | DB first; an `fs_*` id not in the DB (Freesound fallback) is built live from Freesound: one `mix` window, `beat_times: []`, `stems: []` |
| `POST /tracks/{id}/stems` | `StemsRequest` | `StemsResponse` | existing stems covering the range → `stems`; else enqueue job |
| `GET /jobs/{id}` | — | `Job` | poll every 1 s |
| `POST /imports` | multipart `file` (≤ 25 MB; wav, mp3, flac, m4a, ogg), field `session_id` | `ImportResponse` | uploads, inserts a placeholder track, enqueues `analyze`. Imported tracks are private: never returned by `/search`, only by id |
| `POST /why` | `WhyRequest` | `WhyResponse` | cached in `notes`; fallback windows (not in `windows`) are cached in API memory only |
| `POST /events` | `EventRequest` | 204 | |
| `POST /assist` | `AssistRequest` | `AssistResponse` | Gemini function calling over the Op union |

Error codes in use: `not_found`, `bad_request`, `range_too_long`, `clip_is_sliced`, `upload_too_large`,
`unsupported_format`, `upstream_error` (Gemini/Freesound), `rate_limited`, `internal_error` (unhandled server bug, 500).

---

## 7. Search scoring (implemented by WS2)

1. Plan: Gemini structured output → `SearchPlan` (cache by sha256 of normalized text + sorted chip ids).
   Chip filters are merged into the plan deterministically **after** Gemini, so chips always apply.
2. Query vector `q = embed_text([plan.clap_text])`.
3. SQL: filter by `must_tags` ⊆ tags (or ≥ 1 overlap if that returns < 10), not `exclude_tags`, bpm range
   (also accept half/double time), key; stem in `stems_wanted` if given; never `source = 'import'`;
   order by `embedding <=> q`; limit 60.
4. `score = 0.6·sim + 0.2·tag_overlap + 0.1·bpm_fit + 0.1·loopability` (if `prefer_sparse`: subtract `0.15·density`),
   clamped to 0..1, where
   - `sim = clamp(1 − (embedding <=> q), 0, 1)` (cosine similarity);
   - `tag_overlap = |must_tags ∩ tags| / |must_tags|`, or 0.5 when `must_tags` is empty;
   - `bpm_fit` = 1 when there is no `bpm_range` or the track bpm (or half/double) is inside it, falling linearly
     to 0 at 10 bpm outside; 0.5 when the track bpm is null.
5. Keep at most 3 windows per track; snap to 1/2/4/8/16 bars using beat_times.
6. Gemini rerank of the top 20 → final `limit`; fill `why` from `notes` cache.
7. If fewer than 3 results have score > 0.25 → Freesound fallback, normalized into `Result` (`track.source = "freesound"`,
   id `fs_{id}`, window id `fs_{id}:mix:0`, `audio_url` = Freesound `preview-hq-mp3`, window `0..min(duration, 16)` s,
   `fallback_used = true`). Fallback tracks are **not stored** in v1 (not even when picked): `GET /tracks/{id}` and
   `POST /why` serve them live, and a `pick` event only records the event. Exception: `POST /tracks/{id}/stems` on one
   first stores a minimal `tracks` row (preview copied to `tracks/{id}/mix.mp3`, `bpm`/`key` null, no windows) so
   the worker can separate it.

---

## 8. Environment variables (`.env.example`)

```bash
# server / python (api, worker, ingest)
DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres  # SESSION pooler
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=            # server only, never in web/
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.6-flash         # fast + available; 3.8 Flash was overloaded (503) and slower (C9)
GEMINI_DEGRADED=0                     # 1 = skip planner/rerank/why/assist generation (Gemini down or rate-limited)
FREESOUND_API_KEY=
JAMENDO_CLIENT_ID=                    # optional
CLAP_MODEL=laion/larger_clap_general  # the checkpoint the library was ingested with (C8)
CLAP_REVISION=ada0c23a36c4e8582805bb38fec3905903f18b41  # must match ingest + worker + api (C8)
DEMUCS_MODEL=htdemucs
WEB_ORIGIN=http://localhost:3000      # comma-separated allowed origins; `*` matches [a-z0-9-]+ (Vercel previews)
USE_FIXTURES=0                        # 1 = api answers every endpoint from shared/fixtures (no DB, no CLAP)
API_DOMAIN=                           # deploy only: Caddy hostname, e.g. 203-0-113-7.sslip.io or api.example.com

# web (Next.js)
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_USE_FIXTURES=1            # 1 = lib/api returns shared/fixtures, no backend needed
```

---

## 9. Fixtures (`shared/fixtures/`)

One JSON file per response type, valid against the generated schema: `chips.json`, `search.json` (8 results),
`search_empty.json` (0 results, `fallback_used`), `search_fallback.json` (3 low-score results incl. Freesound,
null bpm/key/artist),
`track_detail.json`, `stems_ready.json`, `stems_queued.json`, `job_running.json`, `job_done_stems.json`,
`job_done_analyze.json`, `import.json`, `why.json`, `assist.json`.
Fixture audio lives in `web/public/fixtures/audio/` (synthetic WAVs made by `scripts/make_fixture_audio.py`:
a 90 bpm drum pattern + chord pad, 16 s, plus fake stems). Fixture URLs point to `/fixtures/audio/...`.
`make check-fixtures` validates every fixture against the schema.
