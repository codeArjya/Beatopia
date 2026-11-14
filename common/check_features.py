"""Real-model acceptance check; run before ingest, separately from offline unit tests."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from common.analysis import analyze_track, make_windows, zero_shot_tags
from common.audio import load_mono
from common.clap import CLAP_MODEL, CLAP_REVISION, embed_audio, embed_text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "web/public/fixtures/audio/mix.wav",
    )
    args = parser.parse_args()
    started = time.perf_counter()
    y, sr = load_mono(str(args.fixture))
    features = analyze_track(y, sr)
    windows = make_windows(y, sr, features)
    audio = embed_audio([y], sr)
    texts = embed_text(
        [
            "drum loop",
            "a heavy metal guitar solo",
            "a slow sad piano ballad",
            "a female opera singer",
            "fast electronic dance music",
        ]
    )
    cosine = float(audio[0] @ texts[0])
    similarities = texts[1:] @ texts[1:].T
    unrelated = similarities[np.triu_indices(4, k=1)]
    tags, scores = zero_shot_tags(audio)[0]
    checks = {
        "tempo_90_plus_minus_2": features.bpm is not None and abs(features.bpm - 90) <= 2,
        "three_windows": len(windows) == 3,
        "normalized_512": bool(
            audio.shape == (1, 512)
            and texts.shape == (5, 512)
            and np.allclose(np.linalg.norm(audio, axis=1), 1, atol=1e-5)
            and np.allclose(np.linalg.norm(texts, axis=1), 1, atol=1e-5)
        ),
        "drum_cosine_above_0_2": cosine > 0.2,
        "text_not_collapsed": float(unrelated.mean()) < 0.99,
    }
    print(
        json.dumps(
            {
                "model": CLAP_MODEL,
                "revision": CLAP_REVISION,
                "bpm": features.bpm,
                "key": features.key,
                "windows": len(windows),
                "drum_cosine": cosine,
                "unrelated_text_mean_cosine": float(unrelated.mean()),
                "tags": tags,
                "tag_score_count": len(scores),
                "checks": checks,
                "elapsed_s": round(time.perf_counter() - started, 2),
            },
            indent=2,
        )
    )
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
