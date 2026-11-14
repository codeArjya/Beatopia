"""Bounded four-source Demucs inference; no job-table or public API changes."""

import hashlib
import importlib.metadata
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from demucs.api import Separator

from common import audio

STEMS = ("bass", "drums", "other", "vocals")
SR = 44100


def stereo(path: Path) -> np.ndarray:
    raw = audio._ffmpeg(["-i", str(path.resolve()), "-vn", "-ar", str(SR), "-ac", "2", "-f", "f32le", "pipe:1"])
    y = np.frombuffer(raw, dtype="<f4").reshape(-1, 2).copy()
    if not len(y) or not np.isfinite(y).all():
        raise ValueError("Invalid stereo audio")
    return y


class Engine:
    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        started = time.perf_counter()
        self.separator = self._load(self.device)
        self.load_s = time.perf_counter() - started
        # Legacy checkpoint is content-pinned, including its full hash in every cache identity.
        weights = Path(torch.hub.get_dir()) / "checkpoints" / "955717e8-8726e21a.th"
        if not weights.exists():
            raise ValueError("Expected pinned legacy htdemucs checkpoint; configure TORCH_HOME and HF_HUB_OFFLINE=1")
        digest = hashlib.sha256(weights.read_bytes()).hexdigest()
        if not digest.startswith("8726e21a"):
            raise ValueError("Demucs checkpoint hash mismatch")
        self.identity = {
            "model": "htdemucs",
            "weights_sha256": digest,
            "demucs": importlib.metadata.version("demucs"),
            "torch": torch.__version__,
            "segment": 7,
            "overlap": 0.25,
            "shifts": 1,
            "seed": 0,
        }

    @staticmethod
    def _load(device: str) -> Separator:
        return Separator(model="htdemucs", device=device, shifts=1, split=True, overlap=0.25, segment=7, jobs=0)

    def separate(self, y: np.ndarray) -> tuple[dict[str, np.ndarray], dict]:
        if y.ndim != 2 or y.shape[1] != 2 or not 0 < len(y) <= 180 * SR or not np.isfinite(y).all():
            raise ValueError("Separation requires finite stereo audio of at most 180 seconds")
        tensor = torch.from_numpy(y.T.copy())
        started = time.perf_counter()
        fallback = None
        try:
            torch.manual_seed(0)
            with torch.inference_mode():
                _, output = self.separator.separate_tensor(tensor, SR)
        except Exception as error:
            if self.device == "cpu":
                raise
            fallback = type(error).__name__
            self.device = "cpu"
            self.separator = self._load("cpu")
            torch.manual_seed(0)
            with torch.inference_mode():
                _, output = self.separator.separate_tensor(tensor, SR)
        result = {name: value.detach().cpu().numpy().T for name, value in output.items()}
        if set(result) != set(STEMS) or any(a.shape != y.shape or not np.isfinite(a).all() for a in result.values()):
            raise ValueError("Invalid four-stem separation output")
        return result, {"inference_s": time.perf_counter() - started, "device": self.device, "fallback": fallback}


def encode(y: np.ndarray, path: Path) -> None:
    wav = path.with_suffix(".wav")
    sf.write(wav, y, SR, subtype="FLOAT")
    audio.to_mp3(str(wav), str(path))
    wav.unlink()
