"""Generate the synthetic fixture audio in web/public/fixtures/audio/ (CONTRACT §9).

    uv run --project common python scripts/make_fixture_audio.py      (or: make fixture-audio)

A 16 s, 90 bpm, A-minor loop (6 bars, Am-F-C-G-Am-F): drums + bass + chord pad + a sparse "ooh" vocal.
Writes mix.wav (stereo) plus mono stems drums.wav, bass.wav, other.wav, vocals.wav, all 44.1 kHz 16-bit.
Stems are scaled by the same gain as the mix, so the stems sum (in mono) to the mix. Deterministic (seeded).
"""

import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 90.0
DUR = 16.0
BEAT = 60.0 / BPM
N = int(SR * DUR)
OUT = Path(__file__).resolve().parents[1] / "web" / "public" / "fixtures" / "audio"
rng = np.random.default_rng(90)


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def place(buf: np.ndarray, sound: np.ndarray, t: float) -> None:
    i = int(round(t * SR))
    j = min(N, i + len(sound))
    if i < N:
        buf[i:j] += sound[: j - i]


def env(n: int, attack_s: float, release_s: float) -> np.ndarray:
    e = np.ones(n)
    a, r = max(1, int(attack_s * SR)), max(1, int(release_s * SR))
    e[:a] = np.linspace(0, 1, a)
    e[-r:] *= np.linspace(1, 0, r)
    return e


def kick() -> np.ndarray:
    t = np.arange(int(0.45 * SR)) / SR
    freq = 45 + 75 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 7)


def snare() -> np.ndarray:
    t = np.arange(int(0.25 * SR)) / SR
    noise = rng.standard_normal(len(t))
    noise = noise - np.convolve(noise, np.ones(8) / 8, mode="same")  # crude highpass
    return (0.55 * noise * np.exp(-t * 18) + 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25)) * 0.8


def hat(open_: bool = False) -> np.ndarray:
    t = np.arange(int((0.18 if open_ else 0.05) * SR)) / SR
    noise = np.diff(rng.standard_normal(len(t) + 1))
    return noise * np.exp(-t * (20 if open_ else 80)) * 0.18


def tone(hz: float, dur: float, harmonics: list[float], vibrato: float = 0.0) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    phase = 2 * np.pi * hz * t + (vibrato * np.sin(2 * np.pi * 5.0 * t) if vibrato else 0)
    return sum(a * np.sin((k + 1) * phase) for k, a in enumerate(harmonics))


# Am, F, C, G, Am, F (one chord per bar): (bass midi, chord midis)
PROGRESSION = [
    (45, [57, 60, 64]),
    (41, [57, 60, 65]),
    (48, [60, 64, 67]),
    (43, [59, 62, 67]),
    (45, [57, 60, 64]),
    (41, [57, 60, 65]),
]


def drums() -> np.ndarray:
    buf = np.zeros(N)
    k, s = kick(), snare()
    for bar in range(6):
        t0 = bar * 4 * BEAT
        for b in (0, 2.5, 2.75 if bar % 2 else None):  # boom-bap kick, extra ghost kick every other bar
            if b is not None:
                place(buf, k * (0.6 if b == 2.75 else 1.0), t0 + b * BEAT)
        for b in (1, 3):
            place(buf, s, t0 + b * BEAT)
        for e in range(8):
            place(buf, hat(open_=(e == 7)) * (1.0 if e % 2 == 0 else 0.6), t0 + e * BEAT / 2 + (0.02 if e % 2 else 0))
    return buf


def bass() -> np.ndarray:
    buf = np.zeros(N)
    for bar, (root, _) in enumerate(PROGRESSION):
        t0 = bar * 4 * BEAT
        for b, length in ((0, 1.5), (2.5, 1.0), (3.5, 0.5)):
            note = tone(midi_hz(root), length * BEAT, [1.0, 0.35, 0.12])
            place(buf, np.tanh(1.5 * note) * env(len(note), 0.005, 0.05) * 0.5, t0 + b * BEAT)
    return buf


def pad(detune_cents: float = 0.0) -> np.ndarray:
    buf = np.zeros(N)
    ratio = 2 ** (detune_cents / 1200)
    for bar, (_, chord) in enumerate(PROGRESSION):
        length = 4 * BEAT + 0.15
        voice = sum(tone(midi_hz(m) * ratio, length, [1.0, 0.4, 0.2, 0.1, 0.05]) for m in chord)
        place(buf, voice * env(int(length * SR), 0.25, 0.4) * 0.12, bar * 4 * BEAT)
    return buf


def vocals() -> np.ndarray:
    buf = np.zeros(N)
    # bars 3-4 and 5-6: a slow "ooh" line E5 D5 C5 A4
    for bar0 in (2, 4):
        for i, m in enumerate((76, 74, 72, 69)):
            length = 2 * BEAT
            note = tone(midi_hz(m), length, [1.0, 0.5, 0.25, 0.12], vibrato=0.08)
            place(buf, note * env(len(note), 0.12, 0.25) * 0.09, (bar0 * 4 + i * 2) * BEAT)
    return buf


def write_wav(path: Path, data: np.ndarray) -> None:
    data = np.atleast_2d(data)
    if data.shape[0] < data.shape[1]:
        data = data.T  # (frames, channels)
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stems = {"drums": drums(), "bass": bass(), "other": pad(), "vocals": vocals()}
    pad_r = pad(detune_cents=7.0)  # slight detune on the right channel widens the pad in the mix
    left = stems["drums"] + stems["bass"] + stems["other"] + stems["vocals"] * 0.9
    right = stems["drums"] + stems["bass"] + pad_r + stems["vocals"] * 1.1
    gain = 10 ** (-1 / 20) / max(np.abs(left).max(), np.abs(right).max())  # peak -1 dBFS
    write_wav(OUT / "mix.wav", np.stack([left, right]) * gain)
    for name, sig in stems.items():
        write_wav(OUT / f"{name}.wav", sig * gain)
    print(f"wrote {', '.join(['mix', *stems])} (.wav) to {OUT}")


if __name__ == "__main__":
    main()
