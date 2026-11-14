# CONTRACT §5, copied verbatim. Shared (contract) file: change only via a `contract:` PR.
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

class Job(BaseModel):
    id: str
    kind: Literal["stems", "analyze"]
    status: Literal["queued", "running", "done", "error"]
    progress: float
    output: dict | None = None       # see CONTRACT §3 job output shapes
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
