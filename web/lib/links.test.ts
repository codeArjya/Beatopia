import { describe, expect, it } from "vitest";

import { editorHref, formatSeconds } from "./links";

describe("formatSeconds", () => {
  it("keeps at most millisecond precision and drops trailing zeros", () => {
    expect(formatSeconds(10.667)).toBe("10.667");
    expect(formatSeconds(10.66666666)).toBe("10.667");
    expect(formatSeconds(5.5)).toBe("5.5");
    expect(formatSeconds(0)).toBe("0");
    expect(formatSeconds(-0.0001)).toBe("0");
  });
});

describe("editorHref", () => {
  it("builds the fixed hand-off URL in contract order", () => {
    expect(editorHref({ track: "jam_1532881", start: 0, end: 10.667, stem: "mix" })).toBe(
      "/editor?track=jam_1532881&start=0&end=10.667&stem=mix",
    );
    expect(editorHref({ track: "jam_1532881", start: 5.333, end: 16, stem: "other" })).toBe(
      "/editor?track=jam_1532881&start=5.333&end=16&stem=other",
    );
  });

  it("encodes unusual track ids", () => {
    expect(editorHref({ track: "a b&c", start: 1, end: 2, stem: "drums" })).toBe(
      "/editor?track=a+b%26c&start=1&end=2&stem=drums",
    );
  });
});
