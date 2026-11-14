"use client";

// Search state ⇄ URL (`/?q=…&chips=a,b`). Must render inside <Suspense> (useSearchParams + cacheComponents).
// Local state is the source of truth while the user edits; the URL follows 300 ms later via history.replaceState,
// which Next integrates with its router. An external URL change (Back/Forward, the header logo link) resets state.
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useReducer, useState } from "react";

import { useChips, type SearchParams } from "@/lib/api";

import {
  parseSearchParams,
  SEARCH_DEBOUNCE_MS,
  searchKey,
  searchReducer,
  serializeSearchParams,
  toSearchParams,
  type SearchAction,
  type SearchState,
} from "./state";

/** `value` after it has stopped changing (by `key`) for `ms`. */
export function useDebouncedValue<T>(value: T, key: string, ms: number): T {
  const [settled, setSettled] = useState({ value, key });
  useEffect(() => {
    if (key === settled.key) return;
    const t = setTimeout(() => setSettled({ value, key }), ms);
    return () => clearTimeout(t);
  }, [value, key, ms, settled.key]);
  return settled.value;
}

export type SearchStateApi = {
  state: SearchState;
  dispatch: (a: SearchAction) => void;
  /** Debounced request for useSearch; `null` = idle (nothing typed, no chips) or chips still loading. */
  request: SearchParams | null;
};

export function useSearchState(): SearchStateApi {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const urlState = useMemo(() => parseSearchParams(searchParams.toString()), [searchParams]);
  const urlKey = searchKey(urlState);

  const [state, dispatch] = useReducer(searchReducer, urlState);
  const key = searchKey(state);
  const debounced = useDebouncedValue(state, key, SEARCH_DEBOUNCE_MS);
  const debouncedKey = searchKey(debounced);

  // URL changed: ignore our own write (it equals the debounced state); anything else is navigation → adopt it.
  // State adjusted during render (React's "storing information from previous renders" pattern), not in an effect.
  const [seenUrlKey, setSeenUrlKey] = useState(urlKey);
  if (urlKey !== seenUrlKey) {
    setSeenUrlKey(urlKey);
    if (urlKey !== debouncedKey && urlKey !== key) dispatch({ type: "replace", state: urlState });
  }

  // Drop chip ids that aren't in the /chips vocabulary (stale shared links).
  const chips = useChips();
  const known = useMemo(
    () => (chips.data ? new Set(chips.data.categories.flatMap((c) => c.chips.map((x) => x.id))) : null),
    [chips.data],
  );
  if (known && state.chips.some((c) => !known.has(c))) dispatch({ type: "keepKnown", known });

  // Debounced state → URL. replaceState: typing must not flood the history stack.
  useEffect(() => {
    if (window.location.pathname !== pathname) return; // route already left (hidden <Activity>)
    const next = serializeSearchParams(debounced, window.location.search);
    if (next === window.location.search.replace(/^\?/, "")) return;
    window.history.replaceState(window.history.state, "", next ? `${pathname}?${next}` : pathname);
  }, [debounced, pathname]);

  // Wait for the vocabulary before sending chips, so unknown ids never reach the API (a chips error unblocks).
  const chipsReady = known !== null || chips.isError || debounced.chips.length === 0;
  const request = useMemo(() => {
    if (!chipsReady) return null;
    return toSearchParams(known ? searchReducer(debounced, { type: "keepKnown", known }) : debounced);
  }, [chipsReady, known, debounced]);

  return { state, dispatch, request };
}
