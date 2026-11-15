import { describe, expect, it } from "vitest";

import {
  EMPTY_SEARCH,
  parseSearchParams,
  searchKey,
  searchReducer,
  serializeSearchParams,
  toSearchParams,
  type SearchState,
} from "./state";

const s = (chips: string[], text = ""): SearchState => ({ text, chips });

describe("searchReducer", () => {
  it("adds chips in order and dedupes", () => {
    let st = searchReducer(EMPTY_SEARCH, { type: "add", id: "genre.soul" });
    st = searchReducer(st, { type: "add", id: "inst.keys" });
    const again = searchReducer(st, { type: "add", id: "genre.soul" });
    expect(again).toBe(st);
    expect(st.chips).toEqual(["genre.soul", "inst.keys"]);
  });

  it("removes a chip and the last chip", () => {
    const st = s(["a", "b", "c"]);
    expect(searchReducer(st, { type: "remove", id: "b" }).chips).toEqual(["a", "c"]);
    expect(searchReducer(st, { type: "remove", id: "zz" })).toBe(st);
    expect(searchReducer(st, { type: "removeLast" }).chips).toEqual(["a", "b"]);
    const empty = s([]);
    expect(searchReducer(empty, { type: "removeLast" })).toBe(empty);
  });

  it("moves a chip to the slot of another (both directions)", () => {
    const st = s(["a", "b", "c", "d"]);
    expect(searchReducer(st, { type: "move", id: "a", overId: "c" }).chips).toEqual(["b", "c", "a", "d"]);
    expect(searchReducer(st, { type: "move", id: "d", overId: "b" }).chips).toEqual(["a", "d", "b", "c"]);
    expect(searchReducer(st, { type: "move", id: "a", overId: "a" })).toBe(st);
    expect(searchReducer(st, { type: "move", id: "x", overId: "a" })).toBe(st);
  });

  it("sets text, keeps known chips, clears", () => {
    const st = s(["genre.soul", "bogus.chip"], "dusty");
    expect(searchReducer(st, { type: "setText", text: "dusty keys" }).text).toBe("dusty keys");
    expect(searchReducer(st, { type: "setText", text: "dusty" })).toBe(st);
    expect(searchReducer(st, { type: "keepKnown", known: new Set(["genre.soul"]) }).chips).toEqual(["genre.soul"]);
    const known = searchReducer(st, { type: "keepKnown", known: new Set(["genre.soul", "bogus.chip"]) });
    expect(known).toBe(st);
    expect(searchReducer(st, { type: "clear" })).toEqual(EMPTY_SEARCH);
  });
});

describe("URL codec", () => {
  it("parses q and comma-separated chips, dropping malformed and duplicate ids", () => {
    expect(parseSearchParams("?q=dusty+keys&chips=genre.soul,inst.keys")).toEqual(s(["genre.soul", "inst.keys"], "dusty keys"));
    expect(parseSearchParams("chips=genre.soul,,genre.soul,<script>, inst.keys ")).toEqual(s(["genre.soul", "inst.keys"]));
    expect(parseSearchParams("")).toEqual(EMPTY_SEARCH);
  });

  it("serializes with literal commas and keeps unrelated params", () => {
    expect(serializeSearchParams(s(["genre.soul", "inst.keys"], " dusty keys "))).toBe("q=dusty+keys&chips=genre.soul,inst.keys");
    expect(serializeSearchParams(EMPTY_SEARCH, "fixture=empty&q=old&chips=a")).toBe("fixture=empty");
    expect(serializeSearchParams(s(["a"]), "?fixture=fallback")).toBe("fixture=fallback&chips=a");
  });

  it("round-trips, including commas and symbols in the text", () => {
    const st = s(["mood.melancholy", "tempo.90"], "keys, rhodes & 50% vinyl");
    expect(parseSearchParams(serializeSearchParams(st))).toEqual(st);
  });

  it("searchKey ignores surrounding whitespace", () => {
    expect(searchKey(s(["a"], "keys "))).toBe(searchKey(s(["a"], "keys")));
  });
});

describe("toSearchParams", () => {
  it("is null when idle", () => {
    expect(toSearchParams(EMPTY_SEARCH)).toBeNull();
    expect(toSearchParams(s([], "   "))).toBeNull();
  });

  it("trims text, sends null text for chip-only searches, uses the contract default limit", () => {
    expect(toSearchParams(s([], " keys "))).toEqual({ text: "keys", chips: [], limit: 8 });
    expect(toSearchParams(s(["genre.soul"]))).toEqual({ text: null, chips: ["genre.soul"], limit: 8 });
  });
});
