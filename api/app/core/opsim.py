"""Op chain simulator (CONTRACT §5 "Op chain semantics"): validates ops against the live clip set.

It does not render audio; it tracks which clips exist, which are sliced (rule 2) and checks the arguments that the
Pydantic models can't (slice count vs at, trim bounds, arrange ids). Used by /assist before ops reach the client.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.ops import Arrange, EditorState, Op, Slice, Trim


class OpError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class ChainSim:
    order: list[str] = field(default_factory=list)  # creation order of every clip id
    sliced: set[str] = field(default_factory=set)

    @classmethod
    def from_editor(cls, editor: EditorState) -> ChainSim:
        sim = cls(order=[c.id for c in editor.clips])
        for op in editor.ops:
            try:
                sim.apply(op)
            except OpError:
                pass  # the client's own history is authoritative; only new ops are rejected
        return sim

    def copy(self) -> ChainSim:
        return ChainSim(order=list(self.order), sliced=set(self.sliced))

    def leaves(self) -> list[str]:
        return [c for c in self.order if c not in self.sliced]

    def _target(self, clip: str) -> None:
        if clip not in self.order:
            raise OpError("bad_request", f"unknown clip {clip!r}; clips now: {', '.join(self.leaves()) or 'none'}")
        if clip in self.sliced:
            kids = [c for c in self.order if c.startswith(clip + ".") and c.count(".") == clip.count(".") + 1]
            raise OpError("clip_is_sliced", f"{clip} was sliced; edit its pieces instead ({', '.join(kids)})")

    def apply(self, op: Op) -> None:
        if isinstance(op, Arrange):
            if not op.order:
                raise OpError("bad_request", "arrange needs at least one clip id")
            for clip in op.order:
                self._target(clip)
            return
        self._target(op.clip)
        if isinstance(op, Trim):
            if op.start_s < 0 or op.end_s <= op.start_s:
                raise OpError("bad_request", "trim needs 0 <= start_s < end_s (seconds from the clip start)")
        elif isinstance(op, Slice):
            if (op.count is None) == (op.at is None):
                raise OpError("bad_request", "slice needs exactly one of count or at")
            if op.at is not None:
                if not op.at or any(t <= 0 for t in op.at) or sorted(set(op.at)) != list(op.at):
                    raise OpError("bad_request", "slice.at must be increasing cut times > 0 (seconds from clip start)")
                if len(op.at) > 31:
                    raise OpError("bad_request", "slice makes at most 32 pieces")
            n = op.count if op.count is not None else len(op.at or []) + 1
            self.sliced.add(op.clip)
            self.order.extend(f"{op.clip}.{i}" for i in range(1, n + 1))
