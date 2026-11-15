import type { Active, Over } from "@dnd-kit/core";
import { describe, expect, it } from "vitest";

import { dropActions, parseDragId, SEARCH_BAR_ID, searchAnnouncements, trayDragId } from "./dnd";
import { EMPTY_SEARCH, searchReducer, type SearchState } from "./state";

const apply = (chips: string[], actions: ReturnType<typeof dropActions>): string[] =>
  actions.reduce<SearchState>(searchReducer, { ...EMPTY_SEARCH, chips }).chips;

describe("drag ids", () => {
  it("round-trips tray and pill ids", () => {
    expect(parseDragId(trayDragId("genre.soul"))).toEqual({ from: "tray", chipId: "genre.soul" });
    expect(parseDragId("inst.keys")).toEqual({ from: "pill", chipId: "inst.keys" });
  });
});

describe("dropActions", () => {
  const stack = ["genre.soul", "inst.keys", "mood.melancholy"];

  it("does nothing without a drop target", () => {
    expect(dropActions(trayDragId("inst.drums"), null, stack)).toEqual([]);
    expect(dropActions("inst.keys", undefined, stack)).toEqual([]);
  });

  it("appends a tray chip dropped on the bar", () => {
    expect(apply(stack, dropActions(trayDragId("inst.drums"), SEARCH_BAR_ID, stack))).toEqual([...stack, "inst.drums"]);
    expect(apply([], dropActions(trayDragId("genre.soul"), SEARCH_BAR_ID, []))).toEqual(["genre.soul"]);
  });

  it("inserts a tray chip before the pill it was dropped on", () => {
    expect(apply(stack, dropActions(trayDragId("inst.drums"), "inst.keys", stack))).toEqual([
      "genre.soul",
      "inst.drums",
      "inst.keys",
      "mood.melancholy",
    ]);
  });

  it("ignores a tray chip that is already stacked, or dropped on an unknown target", () => {
    expect(dropActions(trayDragId("inst.keys"), SEARCH_BAR_ID, stack)).toEqual([]);
    expect(dropActions(trayDragId("inst.drums"), "somewhere-else", stack)).toEqual([]);
  });

  it("reorders pills like arrayMove", () => {
    expect(apply(stack, dropActions("genre.soul", "mood.melancholy", stack))).toEqual([
      "inst.keys",
      "mood.melancholy",
      "genre.soul",
    ]);
    expect(apply(stack, dropActions("mood.melancholy", "genre.soul", stack))).toEqual([
      "mood.melancholy",
      "genre.soul",
      "inst.keys",
    ]);
    expect(dropActions("inst.keys", "inst.keys", stack)).toEqual([]);
  });

  it("moves a pill dropped on the bar's empty area to the end", () => {
    expect(apply(stack, dropActions("genre.soul", SEARCH_BAR_ID, stack))).toEqual([
      "inst.keys",
      "mood.melancholy",
      "genre.soul",
    ]);
    expect(dropActions("mood.melancholy", SEARCH_BAR_ID, stack)).toEqual([]);
  });
});

describe("searchAnnouncements", () => {
  const labels: Record<string, string> = { "genre.soul": "Soul", "inst.keys": "Keys", "inst.drums": "Drums" };
  const a = searchAnnouncements((id) => labels[id] ?? id, () => ["genre.soul", "inst.keys"]);
  const active = (id: string) => ({ id }) as unknown as Active;
  const over = (id: string) => ({ id }) as unknown as Over;

  it("names the chip and the outcome", () => {
    expect(a.onDragStart({ active: active(trayDragId("inst.drums")) })).toBe("Picked up Drums.");
    expect(a.onDragEnd({ active: active(trayDragId("inst.drums")), over: over(SEARCH_BAR_ID) })).toBe(
      "Added Drums to search.",
    );
    expect(a.onDragOver({ active: active("genre.soul"), over: over("inst.keys") })).toBe(
      "Soul moved to position 2 of 2.",
    );
    expect(a.onDragCancel({ active: active("genre.soul"), over: null })).toBe("Cancelled. Soul was not moved.");
  });
});
