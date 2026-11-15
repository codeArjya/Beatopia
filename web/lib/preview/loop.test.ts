import { describe, expect, it } from "vitest";

import { LOOP_LOOKAHEAD_S, loopSeekTarget, windowProgress } from "./loop";

describe("loopSeekTarget", () => {
  it("keeps playing inside the window", () => {
    expect(loopSeekTarget(0, 0, 10.667)).toBeNull();
    expect(loopSeekTarget(5, 0, 10.667)).toBeNull();
    expect(loopSeekTarget(10.6, 0, 10.667)).toBeNull();
  });

  it("wraps to start at the end, one frame early", () => {
    expect(loopSeekTarget(10.667, 0, 10.667)).toBe(0);
    expect(loopSeekTarget(10.667 - LOOP_LOOKAHEAD_S, 0, 10.667)).toBe(0);
    expect(loopSeekTarget(11.2, 5.333, 10.667)).toBe(5.333);
  });

  it("wraps when the playhead is clearly before the window", () => {
    expect(loopSeekTarget(0, 5.333, 10.667)).toBe(5.333);
    // A tiny MP3 seek inaccuracy before start is tolerated.
    expect(loopSeekTarget(5.3, 5.333, 10.667)).toBeNull();
  });

  it("handles degenerate windows", () => {
    expect(loopSeekTarget(1, 2, 2)).toBeNull();
    expect(loopSeekTarget(Number.NaN, 0, 4)).toBeNull();
    // Shorter than the lookahead: wrap only once the end is reached.
    expect(loopSeekTarget(0.005, 0, 0.01)).toBeNull();
    expect(loopSeekTarget(0.01, 0, 0.01)).toBe(0);
  });
});

describe("windowProgress", () => {
  it("is a clamped fraction of the window", () => {
    expect(windowProgress(5.333, 5.333, 10.667)).toBe(0);
    expect(windowProgress(8, 5.333, 10.667)).toBeCloseTo(0.5, 2);
    expect(windowProgress(12, 5.333, 10.667)).toBe(1);
    expect(windowProgress(1, 5.333, 10.667)).toBe(0);
    expect(windowProgress(1, 2, 2)).toBe(0);
  });
});
