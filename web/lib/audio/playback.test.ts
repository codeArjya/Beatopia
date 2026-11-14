import { afterEach, expect, it, vi } from "vitest";
import { occurrenceAt, PlaybackController, playbackPosition } from "./playback";
import { evaluate, sourceKey } from "./evaluate";
import { SAMPLE_RATE } from "./types";

afterEach(() => vi.unstubAllGlobals());
it("tracks offset, clamps at end and wraps full arrangement loops", () => {
  expect(playbackPosition(2, 5, 10, false)).toBe(7);
  expect(playbackPosition(8, 5, 10, false)).toBe(10);
  expect(playbackPosition(8, 5, 10, true)).toBe(3);
  expect(playbackPosition(1, 0, 0, true)).toBe(0);
});

const pcm = { sampleRate: SAMPLE_RATE, channels: [new Float32Array(SAMPLE_RATE * 2)] };
function mockContext(resume: () => Promise<void> = async () => {}) {
  const nodes: { connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>; start: ReturnType<typeof vi.fn>; loop: boolean;
    buffer: AudioBuffer | null; onended: (() => void) | null }[] = [];
  const context = { currentTime: 0, destination: {}, resume: vi.fn(resume), close: vi.fn(async () => {}),
    createBuffer: () => ({ copyToChannel: vi.fn() }),
    createBufferSource: () => {
      const node = { connect: vi.fn(), disconnect: vi.fn(), stop: vi.fn(), start: vi.fn(),
        loop: false, buffer: null, onended: null };
      nodes.push(node);
      return node;
    },
  };
  const constructor = vi.fn(function () { return context; });
  vi.stubGlobal("AudioContext", constructor);
  return { context, constructor, nodes };
}
it("creates the context on play, replaces sources on seek, stops and releases nodes/context", async () => {
  const { context, constructor, nodes } = mockContext();
  const player = new PlaybackController();
  expect(constructor).not.toHaveBeenCalled();
  await player.play(pcm, 0.5);
  expect(context.resume).toHaveBeenCalledOnce();
  expect(nodes[0].start).toHaveBeenCalledWith(0, 0.5);
  context.currentTime = 0.25;
  expect(player.position).toBe(0.75);
  await player.play(pcm, 1);
  expect(nodes[0].stop).toHaveBeenCalledOnce();
  expect(nodes[0].disconnect).toHaveBeenCalledOnce();
  expect(nodes[1].start).toHaveBeenCalledWith(0, 1);
  player.seek(0.2);
  expect(player.position).toBe(0.2);
  expect(player.playing).toBe(false);
  player.dispose();
  expect(context.close).toHaveBeenCalledOnce();
});
it("keeps a wrapped position when loop is switched off mid-playback", async () => {
  const { context, nodes } = mockContext();
  const player = new PlaybackController();
  await player.play(pcm, 0, true);
  context.currentTime = 4.5;
  expect(player.position).toBe(0.5);
  player.setLoop(false);
  expect(nodes[0].loop).toBe(false);
  expect(player.position).toBe(0.5);
  context.currentTime = 5;
  expect(player.position).toBe(1);
  player.dispose();
});
it("does not start an obsolete node after an asynchronous context resume", async () => {
  let resume!: () => void;
  const { nodes } = mockContext(() => new Promise<void>((resolve) => { resume = resolve; }));
  const player = new PlaybackController();
  const pending = player.play(pcm);
  player.stop();
  resume();
  await pending;
  expect(nodes).toHaveLength(0);
  player.dispose();
});
it("maps full-render position to clip occurrences at exact boundaries", async () => {
  const source = { track_id: "t", audio_url: "t.wav", start_s: 0, end_s: 2 };
  const result = await evaluate(new Map([[sourceKey(source), { pcm, origin: 0, beatTimes: [], bpm: null }]]), {
    clips: [{ id: "c1", source }], ops: [{ op: "slice", clip: "c1", count: 2, snap: "none" },
      { op: "arrange", order: ["c1.2", "c1.1", "c1.2"] }],
  });
  expect(occurrenceAt(result, 0.5)).toEqual({ id: "c1.2", offset: 0 });
  expect(occurrenceAt(result, 1)).toEqual({ id: "c1.1", offset: 1 });
  expect(occurrenceAt(result, 2.5)).toEqual({ id: "c1.2", offset: 2 });
  expect(occurrenceAt(result, 3)).toBeNull();
});
