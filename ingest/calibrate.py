"""Replay tags from cached embeddings and prepare attributed calibration auditions.

This command never mutates the DB or production checkpoints. Unreviewed auditions
cannot justify changing thresholds, prompts or the vocabulary.
"""

import argparse
import hashlib
import html
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from common import analysis, storage
from ingest import heroes, pipeline, report
from ingest.sources import write_json


def mapping_snapshot(fixture: Path) -> dict:
    categories = analysis._vocab()
    mapping, ids = {}, set()
    chips = report.read_json(fixture)
    for category in chips["categories"]:
        if category["id"] not in categories:
            continue
        for chip in category["chips"]:
            tags = chip["filter"]["tags"]
            if (
                len(tags) != 1
                or tags[0] not in categories[category["id"]]
                or tags[0] in mapping
                or chip["id"] in ids
                or chip["category"] != category["id"]
            ):
                raise ValueError("Fixture chip/raw-tag mapping differs from vocabulary")
            ids.add(chip["id"])
            mapping[tags[0]] = dict(id=chip["id"], category=category["id"], label=chip["label"])
    if set(mapping) != {t for tags in categories.values() for t in tags}:
        raise ValueError("Fixture mapping does not cover every vocabulary tag")
    return {
        "status": "Existing raw tags and fixture mapping; owner acknowledgments recorded in vocab-freeze.json",
        "vocab_sha256": pipeline.fingerprint()["vocab"],
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "categories": {k: len(v) for k, v in categories.items()},
        "tags": mapping,
        "prompt": "a recording of {tag}",
        "selection": "per-category top 3 strictly above population mean + 1 population std; stable vocab-order ties",
        "model": pipeline.fingerprint()["model"],
        "revision": pipeline.fingerprint()["revision"],
    }


def frozen_mapping(fixture: Path, freeze: Path) -> dict:
    current = mapping_snapshot(fixture)
    frozen = report.read_json(freeze)
    if any(current[key] != frozen.get(key) for key in current if key != "status"):
        raise ValueError("Frozen model/vocabulary/chip mapping changed; coordinate with WS2/WS3")
    return frozen


def replay(windows: list[dict], vectors: np.ndarray) -> dict:
    regenerated = analysis.zero_shot_tags(vectors)
    changes = []
    maximum = 0.0
    for old, (tags, scores) in zip(windows, regenerated, strict=True):
        delta = max(abs(scores[tag] - old["tag_scores"][tag]) for tag in scores)
        maximum = max(maximum, delta)
        if tags != old["tags"] or delta > 1e-5:
            changes.append(dict(id=old["id"], old_tags=old["tags"], replay_tags=tags, max_score_delta=delta))
    return dict(
        windows=len(windows),
        changes=changes,
        max_score_delta=maximum,
        action="recomputed tags from cached audio embeddings; comparison only; no DB/cache writes",
    )


def distinct_examples(windows: list[dict], count: int, reverse: bool = False) -> list[dict]:
    selected, seen = [], set()
    for w in sorted(windows, key=lambda w: (w["density"], w["id"]), reverse=reverse):
        if w["track_id"] not in seen:
            selected.append(w)
            seen.add(w["track_id"])
        if len(selected) == count:
            break
    return selected


def audition_rows(windows: list[dict], hero_ids: set[str], random_ids: set[str]) -> list[dict]:
    selected = {}

    def add(w: dict, reason: str) -> None:
        if w["id"] not in selected:
            selected[w["id"]] = {**w, "selection_reasons": []}
        selected[w["id"]]["selection_reasons"].append(reason)

    for stem in ("mix", "other"):
        group = [w for w in windows if w["stem"] == stem]
        for dense in (False, True):
            for w in distinct_examples(group, 4, reverse=dense):
                add(w, f"{stem}: {'high' if dense else 'low'} density proxy; listening unreviewed")
    groups = {
        "horns": {"horns", "trumpet", "trombone", "saxophone"},
        "keys": {"piano", "rhodes", "organ", "wurlitzer", "clavinet", "harpsichord", "mellotron"},
        "strings": {"strings", "violin", "cello", "harp"},
    }
    for name, tags in groups.items():
        candidates = [w for w in windows if set(w["tags"]) & tags and w["stem"] in {"mix", "other"}]
        candidates.sort(key=lambda w: (-max(w["tag_scores"].get(t, -1) for t in tags), w["id"]))
        seen = set()
        for w in candidates:
            if w["track_id"] not in seen:
                add(w, f"{name}: selected-tag score example; audible prominence unverified")
                seen.add(w["track_id"])
            if len(seen) == 3:
                break
    # One required-timbre candidate per completed hero, capped at the original 30-track gate.
    seen = set()
    candidates = [w for w in windows if w["track_id"] in hero_ids and set(w["tags"]) & heroes.TIMBRES]
    candidates.sort(key=lambda w: (-max(w["tag_scores"].get(t, -1) for t in heroes.TIMBRES), w["id"]))
    for w in candidates:
        if w["track_id"] not in seen:
            add(w, "hero prominent-timbre review candidate; numerical evidence only")
            seen.add(w["track_id"])
        if len(seen) == 30:
            break
    for w in windows:
        if w["id"] in random_ids:
            add(w, "seed-5 random audit window")
    return list(selected.values())


def measurements(w: dict, path: Path, root: Path) -> dict:
    with sf.SoundFile(path) as source:
        sr = source.samplerate
        source.seek(round(w["start_s"] * sr))
        samples = source.read(round((w["end_s"] - w["start_s"]) * sr), dtype="float32", always_2d=True)
    y = samples.mean(axis=1)
    if not len(y) or not np.isfinite(y).all():
        raise ValueError("Empty or nonfinite audition")
    flatness = float(librosa.feature.spectral_flatness(y=y)[0].mean())
    onsets = librosa.onset.onset_detect(y=y, sr=sr)
    result = dict(
        decoded_rms=float(np.sqrt(np.mean(y.astype(np.float64) ** 2))),
        spectral_flatness=flatness,
        onsets_per_second=len(onsets) / (len(y) / sr),
        scope="chunk-local measurements; onset boundary context differs from full-excerpt analysis",
    )
    if (root / "heroes" / w["track_id"] / "manifest.json").exists():
        levels = {}
        for stem in heroes.STEMS:
            with sf.SoundFile(root / "heroes" / w["track_id"] / f"{stem}.mp3") as source:
                source.seek(round(w["start_s"] * sr))
                chunk = source.read(len(y), dtype="float32", always_2d=True)
            levels[stem] = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        result["stem_rms"] = levels
        result["active_stem_fraction_above_minus30_dbfs"] = sum(v > 10 ** (-30 / 20) for v in levels.values()) / 4
    return result


def write_audition(path: Path, examples: list[dict]) -> None:
    def escape(value: object) -> str:
        return html.escape(str(value), quote=True)

    cards = []
    for w in examples:
        cards.append(
            f"<article><h2>{escape(w['id'])}</h2><p>{escape(w['title'])} — {escape(w['artist'])}</p>"
            f"<p>{escape('; '.join(w['selection_reasons']))}</p>"
            f"<p>{escape(w['tags'])} | density proxy {w['density']:.6f} | "
            f"{w['start_s']:.3f}–{w['end_s']:.3f}s</p>"
            f'<audio controls preload="none" data-start="{w["start_s"]}" data-end="{w["end_s"]}" '
            f'src="{escape(w["audio_url"])}"></audio><p>{escape(w["attribution"])}</p>'
            f"<p>{escape(w['license'])} | Listening: unreviewed</p></article>"
        )
    path.write_text(
        '<!doctype html><meta charset="utf-8"><title>Beatopia calibration auditions</title>'
        "<style>body{font:16px system-ui;max-width:1000px;margin:32px auto;padding:0 20px}"
        "article{border-top:1px solid #ccc;padding:16px 0}audio{width:100%}</style>"
        "<h1>Calibration auditions</h1><p>Tags and density are measured proxies. All listening judgments "
        "remain unreviewed. Audio uses the processed track timeline, with playback bounded to each window.</p>"
        + "".join(cards)
        + '<script>document.querySelectorAll("audio").forEach(a=>{'
        'a.addEventListener("play",()=>{document.querySelectorAll("audio").forEach(b=>{if(b!==a)b.pause()});'
        "if(a.currentTime<+a.dataset.start||a.currentTime>=+a.dataset.end)a.currentTime=+a.dataset.start});"
        'a.addEventListener("timeupdate",()=>{if(a.currentTime>=+a.dataset.end)a.pause()});});</script>',
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("ingest/data/session5/report-task9.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("ingest/data"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    mapping = frozen_mapping(Path("shared/fixtures/chips.json"), Path(__file__).with_name("vocab-freeze.json"))
    audit = report.read_json(args.report)
    windows, metadata, replayed = [], {}, []
    hero_ids = set(audit["acceptance"]["verified_hero_ids"])
    for record in audit["track_audit"]:
        if not record["mix_verified"] or record["issues"]:
            continue
        tid = record["id"]
        directory = args.data_dir / "tracks" / tid
        mix = report.read_json(directory / "manifest.json")
        if mix["fingerprint"] != pipeline.fingerprint():
            raise ValueError("Calibration checkpoint differs from audited model/vocab")
        vectors = pipeline.validate(mix, directory)
        group = [{**w, "track_id": tid, "stem": "mix"} for w in mix["windows"]]
        metadata[tid] = {**mix["source"], "attribution": mix["attribution"]}
        if tid in hero_ids:
            hdir = args.data_dir / "heroes" / tid
            manifest = report.read_json(hdir / "manifest.json")
            manifest, hv = heroes.cached(hdir, manifest["identity"], mix)
            group += [{**w, "track_id": tid} for w in manifest["windows"]]
            vectors = np.concatenate([vectors, hv])
        replayed.append(dict(id=tid, **replay(group, vectors)))
        windows.extend(group)
    examples = audition_rows(windows, hero_ids, {w["id"] for w in audit["random_windows"]})
    for w in examples:
        tid, stem = w["track_id"], w["stem"]
        local = args.data_dir / ("tracks" if stem == "mix" else "heroes") / tid / f"{stem}.mp3"
        w.update({k: metadata[tid][k] for k in ("title", "artist", "license", "attribution", "source")})
        w["audio_url"] = storage.public_url(
            f"tracks/{tid}/mix.mp3" if stem == "mix" else f"tracks/{tid}/stems/{stem}.mp3"
        )
        w["measurements"] = measurements(w, local, args.data_dir)
        w["listening"] = "unreviewed"
    result = {
        "time": datetime.now(UTC).isoformat(),
        "audit_snapshot_at": audit["snapshot_at"],
        "audit_sha256": hashlib.sha256(args.report.read_bytes()).hexdigest(),
        "mapping": mapping,
        "retag_replay": replayed,
        "replayed_windows": sum(r["windows"] for r in replayed),
        "changed_windows": sum(len(r["changes"]) for r in replayed),
        "decision": (
            "Keep current prompts/thresholds/vocabulary. No reviewed listening labels justify tuning. "
            "No DB/cache mutation."
        ),
        "density_quantiles_by_stem": {
            stem: np.quantile([w["density"] for w in windows if w["stem"] == stem], [0, 0.1, 0.5, 0.9, 1]).tolist()
            for stem in sorted({w["stem"] for w in windows})
        },
        "examples": examples,
        "audibly_verified_prominent_timbres": 0,
        "human_review": (
            "pending; supply window ID, reviewer, date, audible instruments, sparse/dense judgment and usefulness"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    write_audition(args.output.with_suffix(".html"), examples)
    print(json.dumps({k: result[k] for k in ("time", "replayed_windows", "changed_windows", "decision")}, indent=2))
    if result["changed_windows"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"stage": "calibrate", "error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
