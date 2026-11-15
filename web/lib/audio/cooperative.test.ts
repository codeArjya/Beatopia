import { expect, it } from "vitest";
import { RenderWork } from "./cooperative";
import * as pure from "./ops";
import { SAMPLE_RATE } from "./types";

it("preserves pure-op samples for silence, single frames, mono/stereo, fades and loops", async () => {
  const work = new RenderWork();
  for (const samples of [[0], [0.5], [0, -0.5, 0.25, 1], [0, 0, 0, 0]]) for (const channels of [1, 2]) {
    const pcm = { sampleRate: SAMPLE_RATE, channels: Array.from({ length: channels }, () => Float32Array.from(samples)) };
    for (const [op, expected] of [
      [{ op: "reverse", clip: "c1" }, pure.reverse(pcm)],
      [{ op: "gain", clip: "c1", db: -3 }, pure.gain(pcm, -3)],
      [{ op: "normalize", clip: "c1", peak_db: -1 }, pure.normalize(pcm)],
      [{ op: "fade_in", clip: "c1", ms: 1000 / SAMPLE_RATE }, pure.fadeIn(pcm, 1000 / SAMPLE_RATE)],
      [{ op: "fade_out", clip: "c1", ms: 0 }, pure.fadeOut(pcm, 0)],
      [{ op: "loop", clip: "c1", times: 2 }, pure.loop(pcm, 2)],
    ] as const) expect(await work.pure(pcm, op)).toEqual(expected);
  }
});

it("yields between sample chunks and cancels without finishing a long pure op", async () => {
  const controller = new AbortController();
  let yields = 0;
  const work = new RenderWork(controller.signal, async () => { yields++; controller.abort(); });
  const pcm = { sampleRate: SAMPLE_RATE, channels: [new Float32Array(60 * SAMPLE_RATE)] };
  await expect(work.pure(pcm, { op: "normalize", clip: "c1", peak_db: -1 })).rejects.toMatchObject({ name: "AbortError" });
  expect(yields).toBe(1);
});
