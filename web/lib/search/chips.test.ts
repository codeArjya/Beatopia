import { describe, expect, it } from "vitest";

import chipsFixture from "@fixtures/chips.json";
import type { ChipsResponse } from "@/lib/types/api";

import { filterCategories, indexChips } from "./chips";

const { categories } = chipsFixture as ChipsResponse;
const labels = (q: string) => filterCategories(categories, q).flatMap((c) => c.chips.map((x) => x.label));

describe("indexChips", () => {
  it("indexes every chip with its category color", () => {
    const idx = indexChips(categories);
    expect(idx.size).toBe(categories.reduce((n, c) => n + c.chips.length, 0));
    expect(idx.get("genre.soul")).toMatchObject({ label: "Soul", color: "--chip-genre" });
  });
});

describe("filterCategories", () => {
  it("returns all categories for a blank query", () => {
    expect(filterCategories(categories, "  ")).toHaveLength(5);
  });

  it("matches word prefixes case-insensitively and drops empty categories", () => {
    const res = filterCategories(categories, "GUIT");
    expect(res.map((c) => c.id)).toEqual(["instrument"]);
    expect(res[0].chips.map((c) => c.label)).toEqual([
      "Bass guitar",
      "Electric guitar",
      "Acoustic guitar",
      "Wah guitar",
      "Slide guitar",
    ]);
  });

  it("requires every word, and tolerates punctuation", () => {
    expect(labels("c# min")).toEqual(["C# minor"]);
    expect(labels("hihat")).toEqual(["Hi-hats"]);
    expect(labels("lo fi")).toEqual(["Lo-fi"]);
    expect(labels("90")).toEqual(["90 BPM"]);
    expect(labels("zzz")).toEqual([]);
  });
});
