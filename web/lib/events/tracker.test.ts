import { describe, expect, it } from "vitest";

import { createPlayTracker, isPreviewStart, SKIP_WINDOW_MS } from "./tracker";

describe("createPlayTracker", () => {
  it("sends play once per card per query", () => {
    const t = createPlayTracker();
    expect(t.play("w1", "q1", 0)).toEqual([{ action: "play", window_id: "w1", query_id: "q1" }]);
    expect(t.play("w1", "q1", 10_000)).toEqual([]);
    expect(t.play("w1", "q2", 20_000)).toEqual([{ action: "play", window_id: "w1", query_id: "q2" }]);
  });

  it("sends skip for the previous card when another starts within 1.5 s", () => {
    const t = createPlayTracker();
    t.play("w1", "q1", 1000);
    expect(t.play("w2", "q1", 1000 + SKIP_WINDOW_MS - 1)).toEqual([
      { action: "skip", window_id: "w1", query_id: "q1" },
      { action: "play", window_id: "w2", query_id: "q1" },
    ]);
  });

  it("no skip at or after 1.5 s, or when the same card restarts", () => {
    const t = createPlayTracker();
    t.play("w1", "q1", 0);
    expect(t.play("w2", "q1", SKIP_WINDOW_MS)).toEqual([{ action: "play", window_id: "w2", query_id: "q1" }]);
    expect(t.play("w2", "q1", SKIP_WINDOW_MS + 100)).toEqual([]);
  });

  it("a quick skip back to an already-played card sends only the skip", () => {
    const t = createPlayTracker();
    t.play("w1", "q1", 0);
    t.play("w2", "q1", 5000);
    expect(t.play("w1", "q1", 5500)).toEqual([{ action: "skip", window_id: "w2", query_id: "q1" }]);
  });

  it("keeps a null query id", () => {
    expect(createPlayTracker().play("w1", null, 0)).toEqual([{ action: "play", window_id: "w1", query_id: null }]);
  });
});

describe("isPreviewStart", () => {
  it("is true when an item becomes active or a different item takes over", () => {
    expect(isPreviewStart({ id: null, active: false }, { id: "a", active: true })).toBe(true);
    expect(isPreviewStart({ id: "a", active: false }, { id: "a", active: true })).toBe(true);
    expect(isPreviewStart({ id: "a", active: true }, { id: "b", active: true })).toBe(true);
  });
  it("is false for loading → playing of the same item, or stops", () => {
    expect(isPreviewStart({ id: "a", active: true }, { id: "a", active: true })).toBe(false);
    expect(isPreviewStart({ id: "a", active: true }, { id: "a", active: false })).toBe(false);
    expect(isPreviewStart({ id: "a", active: true }, { id: null, active: false })).toBe(false);
  });
});
