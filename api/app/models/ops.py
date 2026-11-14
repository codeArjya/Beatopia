# CONTRACT §5, copied verbatim (only the imports are added). Shared (contract) file: change only via a `contract:` PR.
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .api import StemName

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
