import { describe, expect, it } from "vitest";
import { createEditorStore } from "./editor";
import { sourceKey } from "../lib/audio/evaluate";
import { SAMPLE_RATE } from "../lib/audio/types";

async function setup() {
  const store = createEditorStore();
  const source = { track_id: "t", audio_url: "t.wav", start_s: 0, end_s: 4 / SAMPLE_RATE };
  await store.getState().initialize({ bpm: 90, clips: [{ id: "c1", source }], ops: [], arrangement: [] },
    new Map([[sourceKey(source), { origin: 0, beatTimes: [], bpm: 90,
      pcm: { sampleRate: SAMPLE_RATE, channels: [Float32Array.from([1, 2, 3, 4])] } }]]));
  return store;
}
describe("editor transactions", () => {
  it("groups a sequential batch, restores wire and render on undo/redo, and clears redo on new edit", async () => {
    const store = await setup();
    const before = store.getState().toEditorState();
    await store.getState().apply([{ op: "slice", clip: "c1", count: 2, snap: "none" }, { op: "reverse", clip: "c1.2" }]);
    const after = store.getState().toEditorState();
    const render = Array.from(store.getState().current!.evaluation.rendered.channels[0]);
    expect(render).toEqual([1, 2, 4, 3]);
    expect(store.getState().past).toHaveLength(1);
    store.getState().undo();
    expect(store.getState().toEditorState()).toEqual(before);
    expect(Array.from(store.getState().current!.evaluation.rendered.channels[0])).toEqual([1, 2, 3, 4]);
    store.getState().redo();
    expect(store.getState().toEditorState()).toEqual(after);
    expect(Array.from(store.getState().current!.evaluation.rendered.channels[0])).toEqual(render);
    store.getState().undo();
    await store.getState().apply([{ op: "reverse", clip: "c1" }]);
    expect(store.getState().future).toEqual([]);
  });
  it("failed batch leaves audio, wire and history untouched", async () => {
    const store = await setup();
    const current = store.getState().current;
    await store.getState().apply([{ op: "reverse", clip: "c1" }, { op: "reverse", clip: "absent" }]);
    expect(store.getState().current).toBe(current);
    expect(store.getState().past).toEqual([]);
    expect(store.getState().error).toContain("does not exist");
  });
  it("ignores superseded renders and reset cancels publication", async () => {
    const store = await setup();
    const pending = store.getState().apply([{ op: "reverse", clip: "c1" }]);
    store.getState().reset();
    await pending;
    expect(store.getState().current).toBeNull();
  });
});
