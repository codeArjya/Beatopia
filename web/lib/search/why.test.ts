import { describe, expect, it } from "vitest";

import { shouldRequestWhy, whyView } from "./why";

describe("whyView", () => {
  it("shows a cached or fetched note whatever else is true", () => {
    expect(whyView({ note: "Loops cleanly.", requested: false, isError: false })).toBe("note");
    expect(whyView({ note: "Loops cleanly.", requested: true, isError: true })).toBe("note");
  });

  it("prompts until asked, then loads, then errors", () => {
    expect(whyView({ note: null, requested: false, isError: false })).toBe("prompt");
    expect(whyView({ note: undefined, requested: true, isError: false })).toBe("loading");
    expect(whyView({ note: "", requested: true, isError: true })).toBe("error");
  });
});

describe("shouldRequestWhy", () => {
  it("is false on scroll alone (idle preview, collapsed)", () => {
    expect(shouldRequestWhy(false, false, "idle")).toBe(false);
    expect(shouldRequestWhy(false, false, "error")).toBe(false);
  });

  it("is true on first expand or first play, and stays true", () => {
    expect(shouldRequestWhy(false, true, "idle")).toBe(true);
    expect(shouldRequestWhy(false, false, "loading")).toBe(true);
    expect(shouldRequestWhy(false, false, "playing")).toBe(true);
    expect(shouldRequestWhy(true, false, "idle")).toBe(true);
  });
});
