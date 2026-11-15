import { describe, expect, it, vi } from "vitest";
import type { EditorState, Op } from "../types/api";
import { PrefixCache } from "./cache";
import { evaluate, sourceKey, type OfflineRenderer, type SourceAsset } from "./evaluate";
import { planOfflineFrames } from "./offline";
import { encodeWav } from "./wav";
import { SAMPLE_RATE } from "./types";

const source = { track_id: "cache", audio_url: "cache.wav", start_s: 0, end_s: 16 / SAMPLE_RATE };
const wire = (ops: Op[] = []): EditorState => ({ bpm: 120, clips: [{ id: "c1", source }], ops, arrangement: [] });
const asset: SourceAsset = { origin: 0, bpm: 120, beatTimes: [0, 8 / SAMPLE_RATE],
  pcm: { sampleRate: SAMPLE_RATE, channels: [Float32Array.from({ length: 16 }, (_, i) => (i - 8) / 16)] } };
const registry = new Map([[sourceKey(source), asset]]);
const offline: OfflineRenderer = async (pcm, op, bpm) => ({ ...pcm,
  channels: pcm.channels.map((channel) => Float32Array.from({ length: planOfflineFrames(pcm, op, bpm).frames }, (_, i) => channel[i % channel.length])) });

describe("bounded replay prefixes", () => {
  it("matches fresh PCM, beats, tempo, leaves, repeats and WAV for the complete op union and a branch", async () => {
    const cache = new PrefixCache();
    const ops: Op[] = [
      { op: "gain", clip: "c1", db: -2 }, { op: "fade_in", clip: "c1", ms: 1 },
      { op: "fade_out", clip: "c1", ms: 1 }, { op: "normalize", clip: "c1", peak_db: -1 },
      { op: "reverse", clip: "c1" }, { op: "loop", clip: "c1", times: 2 },
      { op: "trim", clip: "c1", start_s: 2 / SAMPLE_RATE, end_s: 28 / SAMPLE_RATE },
      { op: "repitch", clip: "c1", semitones: -3 }, { op: "pitch_shift", clip: "c1", semitones: 3 },
      { op: "stretch_to_bpm", clip: "c1", target_bpm: 90, keep_pitch: true },
      { op: "filter", clip: "c1", type: "lowpass", freq_hz: 1000 },
      { op: "slice", clip: "c1", count: 2, snap: "none" },
      { op: "arrange", order: ["c1.2", "c1.1", "c1.2"] },
      { op: "slice", clip: "c1.2", count: 2, snap: "none" },
    ];
    for (let count = 0; count <= ops.length; count++) {
      const state = wire(ops.slice(0, count));
      const cached = await evaluate(registry, state, offline, { cache });
      const fresh = await evaluate(registry, state, offline);
      expect(cached).toEqual(fresh);
      expect(encodeWav(cached.rendered)).toEqual(encodeWav(fresh.rendered));
    }
    const branch = wire([...ops.slice(0, 4), { op: "reverse", clip: "c1" }]);
    expect(await evaluate(registry, branch, offline, { cache })).toEqual(await evaluate(registry, branch, offline));
  });
  it("reuses unaffected PCM without replaying offline work, including preview-to-apply", async () => {
    const cache = new PrefixCache(); const render = vi.fn(offline);
    const state = wire([{ op: "slice", clip: "c1", count: 2, snap: "none" }, { op: "pitch_shift", clip: "c1.1", semitones: 3 }]);
    const before = await evaluate(registry, state, render, { cache });
    const next = { ...state, ops: [...state.ops, { op: "reverse", clip: "c1.2" } as const] };
    const after = await evaluate(registry, next, render, { cache });
    expect(after.clips.get("c1.1")).toBe(before.clips.get("c1.1"));
    expect(after.clips.get("c1.2")!.pcm).not.toBe(before.clips.get("c1.2")!.pcm);
    expect(render).toHaveBeenCalledTimes(1);
    expect(await evaluate(registry, next, render, { cache })).toEqual(after);
    expect(render).toHaveBeenCalledTimes(1);
  });
  it("invalidates source identity, origin, beat/BPM values, wire baseline and renderer identity", async () => {
    const cache = new PrefixCache();
    const state = wire([{ op: "reverse", clip: "c1" }]);
    await evaluate(registry, state, undefined, { cache });
    for (const changed of [
      { ...asset, bpm: 90 }, { ...asset, beatTimes: [4 / SAMPLE_RATE] },
      { ...asset, pcm: { ...asset.pcm, channels: [new Float32Array(16).fill(0.2)] } },
      { ...asset, origin: -1 / SAMPLE_RATE, pcm: { ...asset.pcm, channels: [new Float32Array(17).fill(0.5)] } },
    ]) {
      const sources = new Map([[sourceKey(source), changed]]);
      expect(await evaluate(sources, state, undefined, { cache })).toEqual(await evaluate(sources, state));
    }
    const arranged = { ...state, arrangement: ["c1", "c1"] };
    expect(await evaluate(registry, arranged, undefined, { cache })).toEqual(await evaluate(registry, arranged));
    const beats = [0, 8 / SAMPLE_RATE];
    const sameAsset = new Map([[sourceKey(source), { ...asset, beatTimes: beats }]]);
    await evaluate(sameAsset, state, undefined, { cache });
    beats.splice(1, 1, 4 / SAMPLE_RATE);
    expect(await evaluate(sameAsset, state, undefined, { cache })).toEqual(await evaluate(sameAsset, state));
    const dspState = wire([{ op: "pitch_shift", clip: "c1", semitones: 3 }]);
    const render = vi.fn(offline); await evaluate(registry, dspState, render, { cache });
    const different = vi.fn(offline); await evaluate(registry, dspState, different, { cache });
    expect(different).toHaveBeenCalledOnce();
  });
  it("bounds retained buffers and entries, releases on clear, and cannot repopulate after clear during DSP", async () => {
    const cache = new PrefixCache(4096, 2);
    await evaluate(registry, wire([{ op: "reverse", clip: "c1" }, { op: "gain", clip: "c1", db: -1 }]), undefined, { cache });
    expect(cache.stats.entries).toBe(2); expect(cache.stats.bytes).toBeLessThanOrEqual(4096);
    const tiny = new PrefixCache(1, 2);
    expect(await evaluate(registry, wire(), undefined, { cache: tiny })).toEqual(await evaluate(registry, wire()));
    expect(tiny.stats).toEqual({ entries: 0, bytes: 0 });
    let finish!: () => void;
    const pending = evaluate(registry, wire([{ op: "pitch_shift", clip: "c1", semitones: 3 }]), async (pcm) => {
      await new Promise<void>((resolve) => { finish = resolve; }); return pcm;
    }, { cache });
    await expect.poll(() => !!finish).toBe(true);
    cache.clear(); finish(); await pending;
    expect(cache.stats).toEqual({ entries: 0, bytes: 0 });
  });
  it("validates a failing suffix even after a cache hit and preflights excessive allocation", async () => {
    const cache = new PrefixCache(); await evaluate(registry, wire(), undefined, { cache });
    await expect(evaluate(registry, wire([{ op: "reverse", clip: "absent" }]), undefined, { cache })).rejects.toThrow("does not exist");
    const large = { ...source, end_s: 40 };
    const sources = new Map([[sourceKey(large), { ...asset, pcm: { sampleRate: SAMPLE_RATE, channels: [new Float32Array(40 * SAMPLE_RATE)] } }]]);
    const state = { ...wire(), clips: [{ id: "c1", source: large }] };
    await evaluate(sources, state, undefined, { cache });
    await expect(evaluate(sources, { ...state, ops: [{ op: "loop", clip: "c1", times: 2 }] }, undefined, { cache })).rejects.toMatchObject({ code: "range_too_long" });
  });
});
