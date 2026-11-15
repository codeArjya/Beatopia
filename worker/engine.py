"""Bounded Demucs adapter independent of the ingest package."""

import hashlib
import importlib.metadata
import time
from functools import lru_cache

import numpy as np
import torch
from demucs.api import Separator

SR = 44100
FOUR = ("bass", "drums", "other", "vocals")
MODELS = {"htdemucs": FOUR, "htdemucs_6s": (*FOUR, "guitar", "piano")}


class Engine:
    def __init__(self, model: str) -> None:
        if model not in MODELS:
            raise ValueError("Unsupported stem model")
        self.model = model
        self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        started = time.perf_counter()
        self.separator = self.load(self.device)
        self.load_s = time.perf_counter() - started
        # Hash loaded parameters: HF and legacy caches must not silently mix.
        digest = hashlib.sha256()
        for name, value in self.separator.model.state_dict().items():
            digest.update(name.encode())
            digest.update(value.detach().cpu().contiguous().numpy().tobytes())
        self.identity = {
            "model": model,
            "parameters_sha256": digest.hexdigest(),
            "demucs": importlib.metadata.version("demucs"),
            "torch": torch.__version__,
            "segment": 7,
            "overlap": 0.25,
            "shifts": 1,
            "seed": 0,
        }

    def load(self, device: str) -> Separator:
        return Separator(model=self.model, device=device, shifts=1, split=True, overlap=0.25, segment=7, jobs=0)

    def separate(self, y: np.ndarray) -> tuple[dict[str, np.ndarray], dict]:
        if y.ndim != 2 or y.shape[1] != 2 or not 0 < len(y) <= 60 * SR or not np.isfinite(y).all():
            raise ValueError("Separation requires finite stereo audio of at most 60 seconds")
        started = time.perf_counter()
        tensor = torch.from_numpy(y.T.copy())
        fallback = None
        try:
            torch.manual_seed(0)
            with torch.inference_mode():
                _, output = self.separator.separate_tensor(tensor, SR)
        except Exception as error:
            fallback = type(error).__name__
            self.device = "cpu"
            self.separator = self.load("cpu")
            torch.manual_seed(0)
            with torch.inference_mode():
                _, output = self.separator.separate_tensor(tensor, SR)
        result = {name: value.detach().cpu().numpy().T for name, value in output.items()}
        if set(result) != set(MODELS[self.model]) or any(
            value.shape != y.shape or not np.isfinite(value).all() for value in result.values()
        ):
            raise ValueError("Invalid requested-model stem output")
        return result, {"inference_s": time.perf_counter() - started, "device": self.device, "fallback": fallback}


@lru_cache(maxsize=2)
def engine(model: str) -> Engine:
    return Engine(model)
