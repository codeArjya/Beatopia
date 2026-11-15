import { describe, expect, it } from "vitest";

import type { Result } from "@/lib/types/api";

import { adviceFromNote, flipTips, MAX_TIPS, relativeKey, repitchedBpm } from "./flip";

const base = (over: Partial<Pick<Result, "bars" | "stem">> & { bpm?: number | null; key?: string | null } = {}) =>
  ({
    bars: over.bars ?? 4,
    stem: over.stem ?? "mix",
    track: { bpm: over.bpm === undefined ? 90 : over.bpm, key: over.key === undefined ? "A minor" : over.key },
  }) as Pick<Result, "bars" | "stem" | "track">;

describe("adviceFromNote", () => {
  it("keeps advice sentences, in order, at most two", () => {
    const note =
      "Downtempo soul textures with vintage Rhodes. Try adding a low-pass filter to tuck it under drums. " +
      "Chop the chords on the downbeat. Pitch it down two semitones for weight.";
    expect(adviceFromNote(note)).toEqual([
      "Try adding a low-pass filter to tuck it under drums.",
      "Chop the chords on the downbeat.",
    ]);
  });
  it("is empty for missing or descriptive-only notes", () => {
    expect(adviceFromNote(null)).toEqual([]);
    expect(adviceFromNote("A warm, dusty loop with a lazy swing.")).toEqual([]);
  });
});

describe("relativeKey", () => {
  it.each([
    ["A minor", "C major"],
    ["C major", "A minor"],
    ["G# minor", "B major"],
    ["E minor", "G major"],
    ["F major", "D minor"],
    ["Bb major", "G minor"],
  ])("%s → %s", (k, rel) => expect(relativeKey(k)).toBe(rel));
  it("is null for unknown input", () => {
    expect(relativeKey(null)).toBeNull();
    expect(relativeKey("H minor")).toBeNull();
    expect(relativeKey("A dorian")).toBeNull();
  });
});

describe("repitchedBpm", () => {
  it("an octave doubles the tempo", () => {
    expect(repitchedBpm(90, 12)).toBeCloseTo(180);
    expect(repitchedBpm(90, 0)).toBe(90);
  });
});

describe("flipTips", () => {
  it("note advice first, then tempo/key/chop/stem, capped", () => {
    const tips = flipTips("Nice loop. Try layering it under a kick.", base());
    expect(tips.length).toBe(MAX_TIPS);
    expect(tips.map((t) => t.kind)).toEqual(["note", "tempo", "key", "chop"]);
    expect(tips[0].text).toBe("Try layering it under a kick.");
  });

  it("tempo idea depends on the BPM", () => {
    expect(flipTips(null, base({ bpm: 126 }))[0].text).toMatch(/Half-time.*63 BPM/);
    expect(flipTips(null, base({ bpm: 75 }))[0].text).toMatch(/Double-time.*150 BPM/);
    expect(flipTips(null, base({ bpm: 100 }))[0].text).toMatch(/\+2 semitones lands near 112 BPM, −3 slows it to about 84 BPM/);
  });

  it("skips tempo and key when unknown, and chop when the note already says it", () => {
    const tips = flipTips("Chop the first beat.", base({ bpm: null, key: null }));
    expect(tips.map((t) => t.kind)).toEqual(["note", "stem"]);
  });

  it("an isolated stem gets the layering idea", () => {
    const tips = flipTips(null, base({ stem: "bass", bpm: null, key: null }));
    expect(tips.at(-1)).toEqual({ kind: "stem", text: expect.stringMatching(/isolated bass stem/) });
  });
});
