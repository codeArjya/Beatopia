import { describe, expect, it } from "vitest";

import type { Result } from "@/lib/types/api";

import { COVER_FILES, pickCover } from "./cover";

const result = (over: Partial<Pick<Result, "stem" | "tags">> & { id?: string } = {}) =>
  ({
    stem: over.stem ?? "mix",
    tags: over.tags ?? [],
    track: { id: over.id ?? "jam_1" },
  }) as Pick<Result, "stem" | "tags" | "track">;

describe("pickCover", () => {
  it("looks for cover0.jpg to cover5.jpg in public/covers", () => {
    expect(COVER_FILES).toEqual([
      "/covers/cover0.jpg",
      "/covers/cover1.jpg",
      "/covers/cover2.jpg",
      "/covers/cover3.jpg",
      "/covers/cover4.jpg",
      "/covers/cover5.jpg",
    ]);
  });

  it("returns null when no cover files exist", () => {
    expect(pickCover(result({ tags: ["rhodes"] }), [])).toBeNull();
  });

  it("matches the stem first, then tags in order", () => {
    expect(pickCover(result({ stem: "drums", tags: ["rhodes"] }), COVER_FILES)).toBe("/covers/cover2.jpg");
    expect(pickCover(result({ stem: "bass" }), COVER_FILES)).toBe("/covers/cover3.jpg");
    expect(pickCover(result({ tags: ["Melancholy", "Rhodes", "bass"] }), COVER_FILES)).toBe("/covers/cover0.jpg");
    expect(pickCover(result({ tags: ["warm synth pad"] }), COVER_FILES)).toBe("/covers/cover5.jpg");
  });

  it("falls back to a stable pick by track id", () => {
    const first = pickCover(result({ id: "jam_1532881" }), COVER_FILES);
    expect(COVER_FILES).toContain(first);
    expect(pickCover(result({ id: "jam_1532881" }), COVER_FILES)).toBe(first);
    const picks = new Set(Array.from({ length: 40 }, (_, i) => pickCover(result({ id: `track_${i}` }), COVER_FILES)));
    expect(picks.size).toBeGreaterThan(3);
  });

  it("never returns a cover that is missing", () => {
    const only = ["/covers/cover1.jpg", "/covers/cover4.jpg"];
    expect(pickCover(result({ stem: "drums" }), only)).not.toBe("/covers/cover2.jpg");
    for (let i = 0; i < 20; i++) {
      expect(only).toContain(pickCover(result({ id: `t${i}`, stem: "drums", tags: ["rhodes"] }), only));
    }
  });
});
