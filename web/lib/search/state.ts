// Search state: free text + stacked chip ids (order = stacking order, sent as SearchRequest.chips).
// Pure: reducer, URL codec and request derivation. The React hook lives in useSearchState.ts.
import type { SearchParams } from "@/lib/api";

export type SearchState = { text: string; chips: string[] };

export type SearchAction =
  | { type: "add"; id: string }
  | { type: "remove"; id: string }
  | { type: "removeLast" }
  /** Move chip `id` to the position currently held by `overId` (dnd-kit sortable semantics). */
  | { type: "move"; id: string; overId: string }
  | { type: "setText"; text: string }
  /** Drop every chip id not in `known` (the /chips vocabulary). */
  | { type: "keepKnown"; known: ReadonlySet<string> }
  | { type: "replace"; state: SearchState }
  | { type: "clear" };

export const EMPTY_SEARCH: SearchState = { text: "", chips: [] };

/** Matches SearchRequest.limit's default in the contract. */
export const SEARCH_LIMIT = 8;
export const SEARCH_DEBOUNCE_MS = 300;

const CHIP_ID = /^[a-z0-9][a-z0-9_.-]*$/i;

export function searchReducer(state: SearchState, action: SearchAction): SearchState {
  switch (action.type) {
    case "add":
      return state.chips.includes(action.id) ? state : { ...state, chips: [...state.chips, action.id] };
    case "remove":
      return state.chips.includes(action.id) ? { ...state, chips: state.chips.filter((c) => c !== action.id) } : state;
    case "removeLast":
      return state.chips.length ? { ...state, chips: state.chips.slice(0, -1) } : state;
    case "move": {
      const from = state.chips.indexOf(action.id);
      const to = state.chips.indexOf(action.overId);
      if (from < 0 || to < 0 || from === to) return state;
      const chips = [...state.chips];
      chips.splice(to, 0, ...chips.splice(from, 1));
      return { ...state, chips };
    }
    case "setText":
      return action.text === state.text ? state : { ...state, text: action.text };
    case "keepKnown": {
      const chips = state.chips.filter((c) => action.known.has(c));
      return chips.length === state.chips.length ? state : { ...state, chips };
    }
    case "replace":
      return action.state;
    case "clear":
      return state.text === "" && state.chips.length === 0 ? state : EMPTY_SEARCH;
  }
}

/** Read `q` and `chips` (comma-separated) from a query string. Malformed and duplicate chip ids are dropped. */
export function parseSearchParams(params: URLSearchParams | string): SearchState {
  const p = typeof params === "string" ? new URLSearchParams(params) : params;
  const chips: string[] = [];
  for (const raw of (p.get("chips") ?? "").split(",")) {
    const id = raw.trim();
    if (id && CHIP_ID.test(id) && !chips.includes(id)) chips.push(id);
  }
  return { text: p.get("q") ?? "", chips };
}

/**
 * Write the state into `base` (other params such as `?fixture=` are kept), returning the query string without "?".
 * Empty text/chips remove their param. Commas stay literal so the URL reads `chips=genre.soul,inst.keys`.
 */
export function serializeSearchParams(state: SearchState, base: URLSearchParams | string = ""): string {
  const p = new URLSearchParams(base);
  const text = state.text.trim();
  if (text) p.set("q", text);
  else p.delete("q");
  if (state.chips.length) p.set("chips", state.chips.join(","));
  else p.delete("chips");
  return p.toString().replace(/%2C/gi, ",");
}

/** Stable identity of the searchable part of a state (text trimmed). Used to compare URL vs local state. */
export function searchKey(state: SearchState): string {
  return serializeSearchParams(state);
}

/** The request to send, or `null` when there is nothing to search (idle state). */
export function toSearchParams(state: SearchState, limit = SEARCH_LIMIT): SearchParams | null {
  const text = state.text.trim();
  if (!text && state.chips.length === 0) return null;
  return { text: text || null, chips: state.chips, limit };
}
