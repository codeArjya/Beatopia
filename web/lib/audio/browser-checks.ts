/** Development-only Chrome acceptance harness. Node tests do not prove browser DSP. */
import type { TrackDetail } from "../types/api";
import { loadSource } from "./decode";
import { sourceKey } from "./evaluate";
import { renderOffline } from "./native-offline";
import { planOfflineFrames } from "./offline";
import { resolveCuts } from "./slice";
import { SAMPLE_RATE, type PcmBuffer } from "./types";
import { encodeWav } from "./wav";
import { createEditorStore } from "../../stores/editor";

function assert(condition: boolean, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
function tone(frequencies: number[]): PcmBuffer {
  const channel = Float32Array.from({ length: SAMPLE_RATE * 2 }, (_, i) =>
    frequencies.reduce((sum, frequency) => sum + 0.2 * Math.sin(2 * Math.PI * frequency * i / SAMPLE_RATE), 0));
  return { sampleRate: SAMPLE_RATE, channels: [channel, channel.slice()] };
}
function amplitude(pcm: PcmBuffer, frequency: number) {
  const start = Math.round(SAMPLE_RATE * 0.2), end = pcm.channels[0].length - start;
  let real = 0, imaginary = 0;
  // Subsample only the analysis copy; test frequencies stay below its Nyquist.
  for (let i = start; i < end; i += 4) {
    const phase = 2 * Math.PI * frequency * i / SAMPLE_RATE;
    real += pcm.channels[0][i] * Math.cos(phase);
    imaginary += pcm.channels[0][i] * Math.sin(phase);
  }
  return Math.hypot(real, imaginary) * 8 / (end - start);
}
function peakFrequency(pcm: PcmBuffer) {
  let best = 0, strength = 0;
  for (let frequency = 300; frequency <= 650; frequency++) {
    const value = amplitude(pcm, frequency);
    if (value > strength) { best = frequency; strength = value; }
  }
  return best;
}

export async function runBrowserChecks(detail: TrackDetail, report: (line: string) => void): Promise<PcmBuffer> {
  report(`Browser: ${navigator.userAgent}`);
  const input = tone([440]);
  const repitchOp = { op: "repitch", clip: "c1", semitones: -3 } as const;
  const repitched = await renderOffline(input, repitchOp, 90);
  const plan = planOfflineFrames(input, repitchOp, 90);
  const repitchHz = peakFrequency(repitched);
  assert(repitched.channels[0].length === plan.frames && Math.abs(repitchHz - 440 * plan.rate) < 2, "Native repitch pitch/duration failed");
  report(`PASS native -3: rate ${plan.rate}, ${plan.frames} frames, ${repitchHz} Hz`);
  for (const keep_pitch of [false, true]) {
    const fitted = await renderOffline(input, { op: "stretch_to_bpm", clip: "c1", target_bpm: 120, keep_pitch }, 90);
    const frequency = peakFrequency(fitted);
    assert(fitted.channels[0].length === SAMPLE_RATE * 1.5 && Math.abs(frequency - (keep_pitch ? 440 : 440 * 120 / 90)) < 3,
      `Tempo fit failed: keep_pitch=${keep_pitch}, ${fitted.channels[0].length} frames, ${frequency} Hz`);
    report(`PASS 90 to 120 keep_pitch=${keep_pitch}: ${fitted.channels[0].length} frames, ${frequency} Hz`);
  }
  // Simultaneous requests exercise the real shared Tone queue, not parallel global contexts.
  const shifted = await Promise.all([3, -3].map((semitones) => renderOffline(input, { op: "pitch_shift", clip: "c1", semitones }, 90)));
  shifted.forEach((output, i) => {
    const semitones = i === 0 ? 3 : -3, frequency = peakFrequency(output);
    assert(output.channels[0].length === input.channels[0].length && Math.abs(frequency - 440 * 2 ** (semitones / 12)) < 3, "Granular pitch frequency/duration failed");
    assert(output.channels.length === 2 && output.channels[1].some((sample) => sample !== 0), "Granular stereo failed");
    report(`PASS Tone ${semitones}: ${output.channels[0].length} frames, ${frequency} Hz, stereo`);
  });
  const mixed = tone([100, 5000]);
  for (const type of ["lowpass", "highpass"] as const) {
    const filtered = await renderOffline(mixed, { op: "filter", clip: "c1", type, freq_hz: 1000 }, null);
    const pass = amplitude(filtered, type === "lowpass" ? 100 : 5000) / 0.2;
    const stop = amplitude(filtered, type === "lowpass" ? 5000 : 100) / 0.2;
    assert(pass > 0.8 && stop < 0.1 && filtered.channels[0].length === mixed.channels[0].length, "Filter frequency response failed");
    report(`PASS ${type}: pass ${(20 * Math.log10(pass)).toFixed(2)} dB, stop ${(20 * Math.log10(stop)).toFixed(2)} dB`);
  }
  for (const frames of [1, 15, 220, 4410]) {
    const short = { sampleRate: SAMPLE_RATE, channels: [input.channels[0].slice(0, frames)] };
    const output = await renderOffline(short, { op: "pitch_shift", clip: "c1", semitones: 3 }, null);
    assert(output.channels[0].length === frames && output.channels[0].every(Number.isFinite), "Short granular clip failed");
  }
  report("PASS short Tone clips: 1, 15, 220, 4410 frames; finite mono output");
  const source = { track_id: detail.track.id, audio_url: detail.audio_url, start_s: 0, end_s: 16 };
  const pcm = await loadSource(source, 0, new AbortController().signal);
  const cuts = resolveCuts(pcm, { count: 4, snap: "transient" });
  assert(JSON.stringify(cuts) === JSON.stringify(resolveCuts(pcm, { count: 4, snap: "transient" })), "Transient cuts differ");
  report(`PASS fixture transient cuts (frames): ${cuts.join(", ")}`);
  const store = createEditorStore(renderOffline);
  await store.getState().initialize({ clips: [{ id: "c1", source }], ops: [], bpm: 90 },
    new Map([[sourceKey(source), { pcm, origin: 0, beatTimes: detail.beat_times, bpm: 90 }]]));
  await store.getState().apply([{ op: "slice", clip: "c1", count: 4, snap: "none" }]);
  const chopped = store.getState().current;
  await store.getState().apply([{ op: "reverse", clip: "c1.4" }]);
  const reversed = store.getState().current;
  assert(chopped !== reversed && !!reversed, "Golden edits failed");
  store.getState().undo(); assert(store.getState().current === chopped, "Golden undo failed");
  store.getState().redo(); assert(store.getState().current === reversed, "Golden redo failed");
  const golden = reversed.evaluation.rendered;
  assert(golden.channels[0].length === 705600 && golden.channels.length === 2, "Golden frames/channels failed");
  for (let i = 0; i < 705600; i++) for (let channel = 0; channel < 2; channel++) {
    assert(golden.channels[channel][i] === pcm.channels[channel][i < 529200 ? i : 705599 - (i - 529200)], "Golden sample mismatch");
  }
  const wav = encodeWav(golden), header = new DataView(wav);
  assert(header.getUint32(24, true) === SAMPLE_RATE && header.getUint16(34, true) === 16 && wav.byteLength === 2822444, "Golden WAV failed");
  const decoded = await new OfflineAudioContext(2, 1, SAMPLE_RATE).decodeAudioData(wav);
  assert(decoded.length === 705600 && decoded.numberOfChannels === 2, "Chrome WAV decode failed");
  report("PASS H8 engine golden in Chrome: four chops, reverse, undo/redo, all samples, WAV encode/decode; 44100 Hz / 16-bit / stereo / 705600 frames");
  report("Listening and UI workflow acceptance must be recorded separately.");
  return golden;
}
