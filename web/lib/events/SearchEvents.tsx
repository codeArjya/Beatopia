"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { usePostEvent } from "@/lib/api";
import { usePreviewPlayer } from "@/lib/preview/PreviewProvider";

import { createPlayTracker, isPreviewStart } from "./tracker";

type SearchEventsApi = {
  /** The user took this result further (Open in editor, or a stem's Use in editor). */
  pick: (windowId: string) => void;
};

const NOOP: SearchEventsApi = { pick: () => undefined };
const SearchEventsContext = createContext<SearchEventsApi>(NOOP);

/** `pick` for the current search, or a no-op outside <SearchEvents> (e.g. a card rendered elsewhere). */
export function useSearchEvents(): SearchEventsApi {
  return useContext(SearchEventsContext);
}

/**
 * Sends play / skip / pick events (POST /events, fire-and-forget) for the results of one search response.
 * Plays are observed on the shared preview player, so card buttons, Space on a card and shortcuts all count;
 * stem previews ("stem:…" ids) and import previews aren't result windows and are ignored.
 */
export function SearchEvents({
  queryId,
  windowIds,
  children,
}: {
  queryId: string | null;
  windowIds: readonly string[];
  children: ReactNode;
}) {
  const player = usePreviewPlayer();
  const post = usePostEvent();
  const postRef = useRef(post);
  const queryRef = useRef(queryId);
  const idsRef = useRef<ReadonlySet<string>>(new Set(windowIds));
  // Refs are written in an effect (not during render), then read by the long-lived player subscription below.
  useEffect(() => {
    postRef.current = post;
    queryRef.current = queryId;
    idsRef.current = new Set(windowIds);
  });

  // One tracker for the page's lifetime: "first play per card per query" is keyed by query id inside it.
  const [tracker] = useState(createPlayTracker);

  useEffect(() => {
    const view = () => {
      const s = player.getSnapshot();
      return { id: s.item?.id ?? null, active: s.status === "loading" || s.status === "playing" };
    };
    let prev = view();
    return player.subscribe(() => {
      const next = view();
      if (isPreviewStart(prev, next) && next.id && idsRef.current.has(next.id)) {
        for (const e of tracker.play(next.id, queryRef.current, Date.now())) postRef.current(e);
      }
      prev = next;
    });
  }, [player, tracker]);

  const api = useMemo<SearchEventsApi>(
    () => ({ pick: (windowId) => postRef.current({ action: "pick", window_id: windowId, query_id: queryRef.current }) }),
    [],
  );
  return <SearchEventsContext.Provider value={api}>{children}</SearchEventsContext.Provider>;
}
