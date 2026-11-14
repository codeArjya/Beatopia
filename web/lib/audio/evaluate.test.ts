import { describe, expect, it } from "vitest";
import type { EditorState, Op } from "../types/api";
import { evaluate, sourceKey, type SourceRegistry } from "./evaluate";
import { SAMPLE_RATE } from "./types";

const source = { track_id: "test", audio_url: "test.wav", start_s: 5, end_s: 5 + 8 / SAMPLE_RATE };
const registry: SourceRegistry = new Map([[sourceKey(source), {
  pcm: { sampleRate: SAMPLE_RATE, channels: [Float32Array.from([1, 2, 3, 4, 5, 6, 7, 8])] },
  origin: 5, bpm: 90, beatTimes: [5, 5 + 4 / SAMPLE_RATE],
}]]);
const wire = (ops: Op[] = [], arrangement: string[] = []): EditorState => ({ clips: [{ id: "c1", source }], ops, arrangement });
const samples = (evaluation: Awaited<ReturnType<typeof evaluate>>) => Array.from(evaluation.rendered.channels[0]);
describe("non-destructive replay", () => {
  it("derives nested children, keeps source immutable and renders leaves in creation order", async () => {
    const result = await evaluate(registry, wire([
      { op: "slice", clip: "c1", count: 2, snap: "none" },
      { op: "slice", clip: "c1.1", count: 2, snap: "none" },
      { op: "reverse", clip: "c1.1.2" },
    ]));
    expect(result.leaves).toEqual(["c1.1.1", "c1.1.2", "c1.2"]);
    expect(samples(result)).toEqual([1, 2, 4, 3, 5, 6, 7, 8]);
    expect(Array.from(registry.get(sourceKey(source))!.pcm.channels[0])).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });
  it("rejects targeted sliced parents, missing clips and empty/invalid ranges", async () => {
    await expect(evaluate(registry, wire([{ op: "slice", clip: "c1", count: 2, snap: "none" }, { op: "reverse", clip: "c1" }]))).rejects.toMatchObject({ code: "clip_is_sliced" });
    await expect(evaluate(registry, wire([{ op: "reverse", clip: "missing" }]))).rejects.toThrow("does not exist");
    for (const [start_s, end_s] of [[0, 0], [-1, 1], [1, 2]]) {
      await expect(evaluate(registry, wire([{ op: "trim", clip: "c1", start_s, end_s }]))).rejects.toThrow();
    }
  });
  it("replays trims relative to current clip and respects op order", async () => {
    const result = await evaluate(registry, wire([
      { op: "trim", clip: "c1", start_s: 2 / SAMPLE_RATE, end_s: 8 / SAMPLE_RATE },
      { op: "trim", clip: "c1", start_s: 1 / SAMPLE_RATE, end_s: 3 / SAMPLE_RATE },
      { op: "reverse", clip: "c1" },
    ]));
    expect(samples(result)).toEqual([5, 4]);
    const fade: Op = { op: "fade_in", clip: "c1", ms: 8 / SAMPLE_RATE * 1000 };
    const reverse: Op = { op: "reverse", clip: "c1" };
    expect(samples(await evaluate(registry, wire([fade, reverse])))).not.toEqual(samples(await evaluate(registry, wire([reverse, fade]))));
  });
  it("expands repeated arranged parents and later arrange replaces baseline", async () => {
    const sliced: Op = { op: "slice", clip: "c1", count: 2, snap: "none" };
    const baseline = ["c1", "c1"];
    const before = await evaluate(registry, wire([sliced], baseline));
    expect(before.order).toEqual(["c1.1", "c1.2", "c1.1", "c1.2"]);
    const after = await evaluate(registry, wire([sliced, { op: "arrange", order: ["c1.2", "c1.2"] }], baseline));
    expect(samples(after)).toEqual([5, 6, 7, 8, 5, 6, 7, 8]);
    expect(baseline).toEqual(["c1", "c1"]);
  });
  it("maps nonzero source beats through trim, slice and reverse", async () => {
    const result = await evaluate(registry, wire([{ op: "reverse", clip: "c1" }, { op: "slice", clip: "c1", count: 2, snap: "beat" }]));
    expect(result.clips.get("c1.2")!.beatTimes).toEqual([0]);
  });
  it("rejects unavailable DSP and supports injected renderer", async () => {
    const state = wire([{ op: "repitch", clip: "c1", semitones: -3 }]);
    await expect(evaluate(registry, state)).rejects.toThrow("unavailable");
    expect(samples(await evaluate(registry, state, async (pcm) => pcm))).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });
  it("preflights repeated output exceeding sixty seconds", async () => {
    const longSource = { ...source, start_s: 0, end_s: 40 };
    const longRegistry: SourceRegistry = new Map([[sourceKey(longSource), { origin: 0, bpm: null, beatTimes: [],
      pcm: { sampleRate: SAMPLE_RATE, channels: [new Float32Array(40 * SAMPLE_RATE)] } }]]);
    await expect(evaluate(longRegistry, { clips: [{ id: "c1", source: longSource }], ops: [{ op: "arrange", order: ["c1", "c1"] }] })).rejects.toMatchObject({ code: "range_too_long" });
  });
});
