import copy
import json
import sys

import librosa
import numpy as np
import pytest
import soundfile as sf

from common import db
from ingest import density, heroes, pipeline, report, separation, sources
from ingest.separation import SR, STEMS


@pytest.fixture
def measured_cache(tmp_path):
    tid = "jam_42"
    directory, hdir = tmp_path / "tracks" / tid, tmp_path / "heroes" / tid
    directory.mkdir(parents=True)
    hdir.mkdir(parents=True)
    t = np.arange(4 * SR) / SR
    y = np.column_stack([0.1 * np.sin(2 * np.pi * 440 * t)] * 2).astype(np.float32)
    arrays = {s: y * factor for s, factor in zip(STEMS, [1, 1, 0.01, 0.01], strict=True)}
    base = dict(start_s=0, end_s=4, rms=0.1, loopability=0, density=0.01, tags=["piano"], tag_scores={"piano": 0.5})
    mix = dict(
        id=tid,
        duration_s=4,
        audio_sha256="mix",
        fingerprint={"test": "identity"},
        offsets=[dict(processed_start_s=0, processed_end_s=4)],
        windows=[dict(base, id=f"{tid}:mix:0")],
    )
    hw = []
    for stem in STEMS:
        value = heroes.activity_density(arrays[stem], arrays, 0, len(y))
        hw.append(dict(base, id=f"{tid}:{stem}:0", stem=stem, density=value))
        # The decoder/measurement test is codec-independent. Public MP3 probing has separate tests.
        sf.write(hdir / f"{stem}.mp3", arrays[stem], SR, format="WAV", subtype="FLOAT")
    sf.write(directory / "mix.mp3", y, SR, format="WAV", subtype="FLOAT")
    hero = dict(
        identity={"mix_sha256": "mix", "pipeline": mix["fingerprint"]},
        windows=hw,
        hashes={s: heroes.digest(hdir / f"{s}.mp3") for s in STEMS},
    )
    sources.write_json(hdir / "manifest.json", hero)
    receipt = dict(
        method=density.METHOD,
        track_id=tid,
        mix_input_sha256=density.mix_input(mix),
        mix_audio_sha256="mix",
        hero_manifest_sha256=heroes.digest(hdir / "manifest.json"),
        stem_hashes=hero["hashes"],
        densities=density.measure(mix, hero, y, arrays),
        previous_mix_densities={w["id"]: w["density"] for w in mix["windows"]},
    )
    sources.write_json(density.receipt_path(directory), receipt)
    sources.write_json(directory / "manifest.json", mix)
    return tmp_path, mix, hero, receipt, y, arrays


def migrated(mix, receipt):
    result = copy.deepcopy(mix)
    for w in result["windows"]:
        w["density"] = receipt["densities"][w["id"]]
    result["stem_activity_density"] = dict(method=density.METHOD, receipt_sha256=density.sha(receipt))
    return result


def test_measured_mix_uses_two_of_four_active_stems(measured_cache):
    _, mix, _, receipt, y, _ = measured_cache
    spectral = librosa.feature.spectral_flatness(y=y.mean(axis=1))[0].mean()
    assert receipt["densities"][mix["windows"][0]["id"]] == pytest.approx((spectral + 0.5) / 2)
    assert density.mix_input(migrated(mix, receipt)) == density.mix_input(mix)


def test_activity_gate_is_strict_and_uses_stereo_energy():
    limit = 10 ** (-30 / 20)
    y = np.ones((4096, 2)) * 0.1
    arrays = {s: np.zeros_like(y) for s in STEMS}
    arrays["bass"][:] = limit  # Exactly -30 dBFS is not above the activity gate.
    arrays["drums"][:] = [limit * 2, -limit * 2]  # Antiphase stereo still has energy.
    spectral = librosa.feature.spectral_flatness(y=y.mean(axis=1))[0].mean()
    assert heroes.activity_density(y, arrays, 0, len(y)) == pytest.approx((spectral + 0.25) / 2)


@pytest.mark.parametrize("damage", ["missing", "shape", "nan", "join", "range", "stem_density"])
def test_measurement_refuses_invalid_or_changed_inputs(measured_cache, damage):
    _, mix, hero, _, y, arrays = measured_cache
    if damage == "missing":
        arrays.pop("bass")
    elif damage == "shape":
        arrays["bass"] = arrays["bass"][:-1]
    elif damage == "nan":
        arrays["bass"][0, 0] = np.nan
    elif damage == "join":
        mix["offsets"][0]["processed_end_s"] = 2
    elif damage == "range":
        mix["windows"][0]["end_s"] = 5
    else:
        hero["windows"][0]["density"] = 0
    with pytest.raises(ValueError):
        density.measure(mix, hero, y, arrays)


@pytest.mark.parametrize("damage", ["density", "audio", "feature", "marker", "missing_window", "receipt"])
def test_migration_receipt_binds_inputs_and_values(measured_cache, damage):
    root, mix, _, receipt, _, _ = measured_cache
    directory = root / "tracks" / mix["id"]
    updated = migrated(mix, receipt)
    density.validate_mix(updated, directory)
    if damage == "density":
        updated["windows"][0]["density"] = 0
    elif damage == "audio":
        updated["audio_sha256"] = "different"
    elif damage == "feature":
        updated["windows"][0]["tags"] = ["trumpet"]
    elif damage == "marker":
        updated["stem_activity_density"]["receipt_sha256"] = "different"
    elif damage == "missing_window":
        updated["windows"] = []
    else:
        receipt["densities"][mix["windows"][0]["id"]] = float("nan")
        sources.write_json(density.receipt_path(directory), receipt)
    with pytest.raises(ValueError):
        density.validate_mix(updated, directory)


def test_report_redecodes_instead_of_trusting_receipt(measured_cache, monkeypatch):
    root, mix, hero, receipt, _, _ = measured_cache
    rows = [dict(w, stem="mix") for w in mix["windows"]] + copy.deepcopy(hero["windows"])
    assert density.audit(root, mix, hero, rows)["reason"] == "not_migrated"
    updated = migrated(mix, receipt)
    monkeypatch.setattr(
        sf, "read", lambda *_args, **_kwargs: pytest.fail("Density audit must use the canonical decoder")
    )
    for row in rows:
        row["density"] = receipt["densities"][row["id"]]
    result = density.audit(root, updated, hero, rows)
    assert result["verified"] and result["windows"] == 5
    # A consistent DB + receipt + manifest fabrication still fails decoded-audio comparison.
    wid = mix["windows"][0]["id"]
    receipt["densities"][wid] = 0.9
    rows[0]["density"] = 0.9
    sources.write_json(density.receipt_path(root / "tracks" / mix["id"]), receipt)
    with pytest.raises(ValueError, match="measurement"):
        density.audit(root, migrated(mix, receipt), hero, rows)


def test_nonhero_snapshot_checks_exact_recorded_previous_values(measured_cache):
    root, mix, _, receipt, _, _ = measured_cache
    directory = root / "tracks" / mix["id"]
    updated = migrated(mix, receipt)
    previous, migrated_later = density.snapshot_mix_windows(updated, directory, is_hero=False)
    assert migrated_later and previous == mix["windows"]
    current, migrated_later = density.snapshot_mix_windows(updated, directory, is_hero=True)
    assert not migrated_later and current == updated["windows"]
    assert updated["windows"][0]["density"] != previous[0]["density"]
    receipt["previous_mix_densities"] = {}
    sources.write_json(density.receipt_path(directory), receipt)
    with pytest.raises(ValueError, match="snapshot evidence"):
        density.snapshot_mix_windows(migrated(mix, receipt), directory, is_hero=False)


def test_cached_receipt_reuses_measurement_without_inference(measured_cache, monkeypatch):
    root, mix, hero, receipt, _, _ = measured_cache
    monkeypatch.setattr(heroes, "load_mix", lambda *_: (mix, root / "unused"))
    monkeypatch.setattr(pipeline, "validate", lambda *_: np.eye(1, 512))
    monkeypatch.setattr(heroes, "cached", lambda *_: (hero, np.tile(np.eye(1, 512), (4, 1))))
    monkeypatch.setattr(separation, "stereo", lambda *_: pytest.fail("redecoded cached measurement"))
    assert density.prepare(root, mix["id"])[3] == receipt
    hero["hashes"]["bass"] = "changed"
    with pytest.raises(ValueError, match="inputs changed"):
        density.prepare(root, mix["id"])


@pytest.mark.parametrize("damage", [None, "vector", "tags", "missing", "range", "stem", "track", "incomplete_stems"])
def test_transaction_and_crash_recovery_preserve_unrelated_data(measured_cache, monkeypatch, damage):
    root, mix, hero, receipt, _, _ = measured_cache
    vectors = np.tile(np.eye(1, 512, dtype=np.float32), (5, 1))
    rows = [dict(w, stem="mix") for w in mix["windows"]] + copy.deepcopy(hero["windows"])
    for row, v in zip(rows, vectors, strict=True):
        row.update(track_id=mix["id"], embedding=v.copy())
    before = copy.deepcopy(rows)
    if damage == "vector":
        rows[0]["embedding"] *= 2
    elif damage == "tags":
        rows[0]["tags"] = ["invented"]
    elif damage == "missing":
        rows.pop()
    elif damage == "range":
        rows[0]["end_s"] = 5
    elif damage == "stem":
        rows[0]["stem"] = "other"
    elif damage == "track":
        rows[0]["track_id"] = "jam_wrong"
    stems = [
        dict(stem=s, range_start_s=0, range_end_s=4, path=f"tracks/jam_42/stems/{s}.mp3", model="htdemucs")
        for s in STEMS
    ]
    if damage == "incomplete_stems":
        stems.pop()
    monkeypatch.setattr(density, "prepare", lambda *_: (mix, hero, vectors[:1], receipt, vectors[1:]))

    class Connection:
        def __enter__(self):
            self.saved = copy.deepcopy(rows)
            return self

        def __exit__(self, kind, *_):
            if kind:
                rows[:] = self.saved

        def cursor(self, **options):
            assert options["binary"] is True
            return self

        def execute(self, sql, params=None, *, binary=False):
            if "FROM tracks" in sql:
                self.result = [
                    dict(id="jam_42", is_hero=True, source="jamendo", duration_s=4, audio_path="tracks/jam_42/mix.mp3")
                ]
            elif "FROM stems" in sql:
                self.result = stems
            elif "SELECT * FROM windows" in sql:
                self.result = rows
            elif "SELECT id,density" in sql:
                # Model float4 storage and the live server's lossy six-significant-digit text output.
                self.result = [
                    (w["id"], float(np.float32(w["density"])) if binary else float(f"{w['density']:.6g}")) for w in rows
                ]
            elif "UPDATE windows" in sql:
                assert sql == "UPDATE windows SET density=%s WHERE id=%s"
                next(w for w in rows if w["id"] == params[1])["density"] = params[0]
            return self

        def fetchone(self):
            return self.result[0]

        def fetchall(self):
            return self.result

    monkeypatch.setattr(db, "connect", Connection)
    if damage:
        with pytest.raises(ValueError):
            density.apply(root, mix["id"])
        assert "stem_activity_density" not in json.loads((root / "tracks/jam_42/manifest.json").read_text())
        return
    real_write = sources.write_json
    monkeypatch.setattr(sources, "write_json", lambda *_: (_ for _ in ()).throw(OSError("crash after commit")))
    with pytest.raises(OSError, match="crash after commit"):
        density.apply(root, mix["id"])
    monkeypatch.setattr(sources, "write_json", real_write)
    assert density.apply(root, mix["id"])["updated_rows"] == 0
    for old, row in zip(before, rows, strict=True):
        assert row["density"] == pytest.approx(receipt["densities"][row["id"]])
        for key in old.keys() - {"density", "embedding"}:
            assert row[key] == old[key]
        assert np.array_equal(row["embedding"], old["embedding"])
    assert density.mix_input(json.loads((root / "tracks/jam_42/manifest.json").read_text())) == density.mix_input(mix)


def test_follower_probes_real_producer_lock_without_modifying_it(tmp_path):
    path = tmp_path / "heroes/heroes.lock"
    path.parent.mkdir()
    path.write_bytes(b"original-lock")
    assert not density.producer_running(tmp_path)
    with density.file_lock(path):
        assert density.producer_running(tmp_path)
    assert path.read_bytes() == b"original-lock"


def test_report_never_confuses_missing_density_with_completed_coverage():
    result = dict(
        counts={"hero_flags": 2},
        track_audit=[
            dict(
                id="jam_1",
                mix_verified=True,
                hero_cache_verified=True,
                issues=[],
                density_verified=True,
                density_audit={"windows": 5},
            ),
            dict(id="jam_2", mix_verified=True, hero_cache_verified=True, issues=[], density_verified=False),
        ],
    )
    report.finish_report(result, [])
    assert result["hero_density"]["verified_heroes"] == 1
    assert result["hero_density"]["missing_hero_ids"] == ["jam_2"]
    assert not result["acceptance"]["all_completed_hero_density"]
    result["track_audit"][1].update(density_verified=True, density_audit={"windows": 7})
    report.finish_report(result, [])
    assert result["acceptance"]["all_completed_hero_density"]
    assert result["hero_density"]["verified_windows"] == 12


def test_follow_finishes_with_a_sweep_after_producer_shutdown(tmp_path, monkeypatch):
    states = iter([True, False])
    events = []
    monkeypatch.setattr(density, "producer_running", lambda _: next(states))

    def sweep(_):
        events.append("snapshot")
        return {"failures": [], "tracks": [], "verified_heroes": len(events)}

    monkeypatch.setattr(density, "sweep", sweep)
    monkeypatch.setattr(density.time, "sleep", lambda _: None)
    output = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["density", "--data-dir", str(tmp_path), "--output", str(output), "--follow"])
    density.main()
    result = json.loads(output.read_text())
    assert events == ["snapshot", "snapshot"]
    assert result["producer_running_before_snapshot"] is False
    assert result["verified_heroes"] == 2


def test_follow_records_failures_and_exits_without_claiming_completion(tmp_path, monkeypatch):
    output = tmp_path / "result.json"
    monkeypatch.setattr(density, "producer_running", lambda _: True)
    monkeypatch.setattr(density, "sweep", lambda _: {"failures": [{"id": "jam_bad"}], "tracks": []})
    monkeypatch.setattr(sys, "argv", ["density", "--data-dir", str(tmp_path), "--output", str(output), "--follow"])
    with pytest.raises(SystemExit) as error:
        density.main()
    assert error.value.code == 1
    assert json.loads(output.read_text())["failures"] == [{"id": "jam_bad"}]
