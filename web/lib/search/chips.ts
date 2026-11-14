// Pure helpers over the /chips vocabulary (never hardcode chip lists).
import type { Chip, ChipCategory } from "@/lib/types/api";

export type IndexedChip = Chip & { color: string };

/** id → chip plus its category color, for rendering stacked pills from ids. */
export function indexChips(categories: readonly ChipCategory[]): Map<string, IndexedChip> {
  const m = new Map<string, IndexedChip>();
  for (const c of categories) for (const chip of c.chips) m.set(chip.id, { ...chip, color: c.color });
  return m;
}

/** Normalize for matching: lowercase, strip accents and punctuation ("C♯ minor" ~ "c# min", "Hi-hats" ~ "hihat"). */
function norm(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .replace(/♯/g, "#")
    .replace(/♭/g, "b")
    .toLowerCase()
    .replace(/[^a-z0-9#]+/g, " ")
    .trim();
}

/**
 * Categories with only the chips whose label matches every word of `query` (word prefixes); empty categories are
 * dropped. A blank query returns the input unchanged.
 */
export function filterCategories(categories: readonly ChipCategory[], query: string): ChipCategory[] {
  const words = norm(query).split(" ").filter(Boolean);
  if (words.length === 0) return [...categories];
  const matches = (label: string) => {
    const labelWords = norm(label).split(" ");
    const joined = labelWords.join("");
    return words.every((w) => labelWords.some((lw) => lw.startsWith(w)) || joined.startsWith(w));
  };
  return categories
    .map((c) => ({ ...c, chips: c.chips.filter((chip) => matches(chip.label)) }))
    .filter((c) => c.chips.length > 0);
}
