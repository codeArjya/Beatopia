import { describe, expect, it } from "vitest";
import { arrangeOccurrence, editorShortcut } from "./editor-actions";
import { createEditorStore } from "../../stores/editor";
import { sourceKey } from "./evaluate";
import { SAMPLE_RATE } from "./types";

describe("arrangement controls", () => {
  it("reorders a repeated nested leaf, undoes one step and expands each duplicate on a later slice", async () => {
    const source = { track_id: "t", audio_url: "t.wav", start_s: 0, end_s: 8 / SAMPLE_RATE };
    const store = createEditorStore();
    await store.getState().initialize({ clips: [{ id: "c1", source }], ops: [] }, new Map([[sourceKey(source), {
      origin: 0, bpm: null, beatTimes: [], pcm: { sampleRate: SAMPLE_RATE, channels: [Float32Array.from([1, 2, 3, 4, 5, 6, 7, 8])] },
    }]]));
    await store.getState().apply([{ op: "slice", clip: "c1", count: 2, snap: "none" }]);
    const order = () => store.getState().current!.evaluation.order;
    await store.getState().apply(arrangeOccurrence(order(), 0, "duplicate"));
    expect(order()).toEqual(["c1.1", "c1.1", "c1.2"]);
    const before = store.getState().current;
    await store.getState().apply(arrangeOccurrence(order(), 1, "right"));
    expect(order()).toEqual(["c1.1", "c1.2", "c1.1"]);
    store.getState().undo();
    expect(store.getState().current).toBe(before);
    store.getState().redo();
    await store.getState().apply([{ op: "slice", clip: "c1.1", count: 2, snap: "none" }]);
    expect(order()).toEqual(["c1.1.1", "c1.1.2", "c1.2", "c1.1.1", "c1.1.2"]);
    expect(Array.from(store.getState().current!.evaluation.rendered.channels[0])).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4]);
  });
  it("rejects an over-limit duplicate atomically, retaining audio, order and history", async () => {
    const source = { track_id: "t", audio_url: "t.wav", start_s: 0, end_s: 20 };
    const store = createEditorStore();
    await store.getState().initialize({ clips: [{ id: "c1", source }], ops: [] }, new Map([[sourceKey(source), {
      origin: 0, bpm: null, beatTimes: [], pcm: { sampleRate: SAMPLE_RATE, channels: [new Float32Array(20 * SAMPLE_RATE)] },
    }]]));
    await store.getState().apply([{ op: "arrange", order: ["c1", "c1", "c1"] }]);
    const before = store.getState().current, history = store.getState().past;
    expect(before!.evaluation.rendered.channels[0]).toHaveLength(60 * SAMPLE_RATE);
    await store.getState().apply(arrangeOccurrence(before!.evaluation.order, 1, "duplicate"));
    expect(store.getState().error).toContain("60 seconds");
    expect(store.getState().current).toBe(before);
    expect(store.getState().past).toBe(history);
  });
});

describe("keyboard shortcuts", () => {
  const event = { key: "r", ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, repeat: false, isComposing: false };
  it("maps Windows/macOS history and manual editor keys", () => {
    for (const [key, action] of [[" ", "play"], ["s", "slice"], ["R", "reverse"], ["ArrowUp", "up"], ["ArrowDown", "down"], ["e", "export"]]) {
      expect(editorShortcut({ ...event, key }, false)).toBe(action);
    }
    expect(editorShortcut({ ...event, key: "z", ctrlKey: true }, false)).toBe("undo");
    expect(editorShortcut({ ...event, key: "Z", metaKey: true, shiftKey: true }, false)).toBe("redo");
    expect(editorShortcut({ ...event, key: "Z", ctrlKey: true, shiftKey: true }, false)).toBe("redo");
  });
  it("leaves typing, IME, repeats, native browser chords and unassigned keys untouched", () => {
    expect(editorShortcut(event, true)).toBeNull();
    for (const change of [{ repeat: true }, { isComposing: true }, { ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { key: "Tab" }]) {
      expect(editorShortcut({ ...event, ...change }, false)).toBeNull();
    }
  });
});
