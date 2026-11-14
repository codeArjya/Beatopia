import functools
import shutil
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from common.audio import load_mono, to_mp3


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is not on PATH")
    t = np.arange(48000) / 48000
    # Two identical channels preserve amplitude when downmixed.
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    path = tmp_path / "stereo input.wav"
    sf.write(path, np.column_stack([tone, tone]), 48000, subtype="PCM_16")
    return path


def test_decode_resamples_to_finite_float32_mono(audio_file: Path) -> None:
    samples, sr = load_mono(str(audio_file))
    assert sr == 44100
    assert samples.shape == (44100,)
    assert samples.dtype == np.float32
    assert np.isfinite(samples).all()
    assert np.sqrt(np.mean(samples**2)) == pytest.approx(0.25 / np.sqrt(2), abs=0.001)


def test_mono_amplitude_is_preserved(audio_file: Path, tmp_path: Path) -> None:
    stereo, sr = sf.read(audio_file)
    mono = tmp_path / "mono.wav"
    sf.write(mono, stereo[:, 0], sr)
    decoded, _ = load_mono(str(mono))
    assert np.sqrt(np.mean(decoded**2)) == pytest.approx(0.25 / np.sqrt(2), abs=0.001)


def test_mp3_roundtrip_and_repeat(audio_file: Path, tmp_path: Path) -> None:
    output = tmp_path / "tracks" / "mix.mp3"
    for _ in range(2):
        to_mp3(str(audio_file), str(output))
        info = sf.info(output)
        assert info.samplerate == 44100
        assert info.channels == 2
        samples, sr = load_mono(str(output), sr=24000)
        assert sr == 24000
        assert len(samples) == pytest.approx(24000, abs=100)
        assert np.sqrt(np.mean(samples**2)) > 0.15


@pytest.fixture
def audio_server(audio_file: Path) -> Iterator[str]:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(audio_file.parent))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/stereo%20input.wav"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_http_audio_matches_local(audio_file: Path, audio_server: str) -> None:
    local, _ = load_mono(str(audio_file))
    remote, sr = load_mono(audio_server)
    assert sr == 44100
    np.testing.assert_array_equal(remote, local)


def test_failed_transcode_preserves_existing_output(audio_file: Path, tmp_path: Path) -> None:
    destination = tmp_path / "mix.mp3"
    to_mp3(str(audio_file), str(destination))
    original = destination.read_bytes()
    corrupt = tmp_path / "corrupt.wav"
    corrupt.write_bytes(b"not an audio file")
    with pytest.raises(ValueError, match="FFmpeg"):
        to_mp3(str(corrupt), str(destination))
    assert destination.read_bytes() == original
    assert not list(tmp_path.glob(".encode-*"))
    with pytest.raises(ValueError):
        load_mono(str(corrupt))


def test_missing_input(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_mono(str(tmp_path / "missing.wav"))


@pytest.mark.parametrize("sr", [0, -1, True, 44100.5])
def test_invalid_sample_rate(sr: int) -> None:
    with pytest.raises(ValueError, match="Sample rate"):
        load_mono("unused.wav", sr=sr)


def test_missing_ffmpeg(audio_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(RuntimeError, match="FFmpeg is required"):
        load_mono(str(audio_file))


def test_refuses_overwriting_source(audio_file: Path) -> None:
    with pytest.raises(ValueError, match="must differ"):
        to_mp3(str(audio_file), str(audio_file))
