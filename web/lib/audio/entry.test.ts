import { describe, expect, it } from "vitest";
import fixture from "../../../shared/fixtures/track_detail.json";
import { parseEntry, resolveEntry } from "./entry";
import type { TrackDetail } from "../types/api";

describe("editor URL", () => {
  it("loads exact nonzero bounds and only records a matching opaque window", () => {
    const entry = parseEntry(new URLSearchParams("track=jam_1532881&start=5&end=15&stem=mix"));
    const result = resolveEntry(entry, fixture as TrackDetail);
    expect(result.source.start_s).toBe(5);
    expect(result.windowId).toBe("jam_1532881:mix:5000");
    expect(resolveEntry({ ...entry, end: 14 }, fixture as TrackDetail).windowId).toBeUndefined();
  });
  it("validates missing, nonfinite, reversed, long and unsupported input", () => {
    for (const query of ["", "track=t", "track=t&start= &end=4", "track=t&start=0&end=Infinity", "track=t&start=4&end=2", "track=t&start=0&end=61", "track=t&start=0&end=4&stem=nope"]) {
      expect(() => parseEntry(new URLSearchParams(query))).toThrow();
    }
    const entry = { trackId: "jam_1532881", start: 0, end: 16, stem: "mix" as const };
    expect(() => resolveEntry({ ...entry, trackId: "wrong" }, fixture as TrackDetail)).toThrow("fixture");
    expect(() => resolveEntry({ ...entry, end: 17 }, fixture as TrackDetail)).toThrow("beyond");
  });
  it("maps ranged stem origins without changing absolute wire times", () => {
    const detail = structuredClone(fixture) as TrackDetail;
    detail.stems[0].range_start_s = 5;
    const result = resolveEntry({ trackId: "jam_1532881", start: 6, end: 10, stem: "drums" }, detail);
    expect(result.origin).toBe(5);
    expect(result.source.start_s).toBe(6);
  });
});
