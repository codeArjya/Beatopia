import { describe, expect, it, vi } from "vitest";
import { planOfflineFrames, type OfflineOp } from "./offline";
import { SAMPLE_RATE, type PcmBuffer } from "./types";
import { evaluate, sourceKey } from "./evaluate";

const pcm = { sampleRate: SAMPLE_RATE, channels: [new Float32Array(SAMPLE_RATE * 4)] };
describe("offline planning (not DSP verification)", () => {
  it("plans native pitch rate and inverse duration, granular pitch duration and both fits", () => {
    const pitch = planOfflineFrames(pcm, { op: "repitch", clip: "c1", semitones: -3 }, 90);
    expect(pitch.rate).toBe(2 ** (-3 / 12));
    expect(pitch.frames).toBe(Math.round(SAMPLE_RATE * 4 / pitch.rate));
    expect(pitch.granular).toBe(false);
    expect(planOfflineFrames(pcm, { op: "pitch_shift", clip: "c1", semitones: 3 }, 90)).toEqual({ frames: SAMPLE_RATE * 4, rate: 1, semitones: 3, granular: true });
    for (const keep_pitch of [false, true]) {
      expect(planOfflineFrames(pcm, { op: "stretch_to_bpm", clip: "c1", target_bpm: 120, keep_pitch }, 90))
        .toEqual({ frames: SAMPLE_RATE * 3, rate: 120 / 90, semitones: 0, granular: keep_pitch });
    }
    expect(planOfflineFrames(pcm, { op: "filter", clip: "c1", type: "highpass", freq_hz: 1000 }, null).frames).toBe(SAMPLE_RATE * 4);
  });
  it("rejects missing BPM, nonfinite/out-of-range values, empty PCM and output over sixty seconds", () => {
    for (const bpm of [null, 0, NaN, Infinity]) expect(() => planOfflineFrames(pcm, { op: "stretch_to_bpm", clip: "c1", target_bpm: 120 }, bpm)).toThrow("known source BPM");
    for (const semitones of [-25, 25, NaN]) expect(() => planOfflineFrames(pcm, { op: "repitch", clip: "c1", semitones }, 90)).toThrow();
    for (const freq_hz of [19, 20001, Infinity]) expect(() => planOfflineFrames(pcm, { op: "filter", clip: "c1", type: "lowpass", freq_hz }, 90)).toThrow();
    expect(() => planOfflineFrames({ ...pcm, channels: [new Float32Array(0)] }, { op: "repitch", clip: "c1", semitones: 0 }, 90)).toThrow("nonempty");
    expect(() => planOfflineFrames({ ...pcm, channels: [new Float32Array(SAMPLE_RATE * 16)] }, { op: "repitch", clip: "c1", semitones: -24 }, 90)).toThrow("60 seconds");
  });
  it("dispatches every offline variant with original track BPM and maps beats through rate changes", async () => {
    const source = { track_id: "t", audio_url: "t.wav", start_s: 0, end_s: 4 };
    const registry = new Map([[sourceKey(source), { pcm, bpm: 90, beatTimes: [0, 1, 2, 3], origin: 0 }]]);
    const operations: OfflineOp[] = [
      { op: "repitch", clip: "c1", semitones: -12 },
      { op: "pitch_shift", clip: "c1", semitones: 3 },
      { op: "filter", clip: "c1", type: "lowpass", freq_hz: 1000 },
      { op: "stretch_to_bpm", clip: "c1", target_bpm: 120, keep_pitch: false },
      { op: "stretch_to_bpm", clip: "c1", target_bpm: 120, keep_pitch: true },
    ];
    const called: OfflineOp[] = [];
    const result = await evaluate(registry, { clips: [{ id: "c1", source }], ops: operations }, async (input, op, bpm) => {
      expect(bpm).toBe(90); called.push(op);
      return { ...input, channels: input.channels.map(() => new Float32Array(planOfflineFrames(input, op, bpm).frames)) };
    });
    expect(called).toEqual(operations);
    expect(result.rendered.channels[0].length).toBe(SAMPLE_RATE * 4.5);
    expect(result.clips.get("c1")!.beatTimes.map((time) => time * SAMPLE_RATE)).toEqual([0, Math.round(1.125 * SAMPLE_RATE), 2.25 * SAMPLE_RATE, Math.round(3.375 * SAMPLE_RATE)]);
    expect(result.clips.get("c1")!.tempoBpm).toBe(80);
  });
  it("preflights repeated arrangement duration before DSP and rejects malformed renderer output", async () => {
    const source = { track_id: "t", audio_url: "t.wav", start_s: 0, end_s: 4 };
    const registry = new Map([[sourceKey(source), { pcm, bpm: 90, beatTimes: [], origin: 0 }]]);
    const offline = vi.fn(async (input: PcmBuffer) => input);
    await expect(evaluate(registry, { clips: [{ id: "c1", source }], arrangement: Array(4).fill("c1"), ops: [
      { op: "repitch", clip: "c1", semitones: -24 },
    ] }, offline)).rejects.toMatchObject({ code: "range_too_long" });
    expect(offline).not.toHaveBeenCalled();
    await expect(evaluate(registry, { clips: [{ id: "c1", source }], ops: [
      { op: "repitch", clip: "c1", semitones: -12 },
    ] }, offline)).rejects.toThrow("unexpected frames or channels");
  });
});
