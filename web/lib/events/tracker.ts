// Pure rules for search analytics events (POST /events, CONTRACT EventRequest). No React, no network.

import type { EventRequest } from "@/lib/types/api";

/** A card started within this long of the previous card's start counts as skipping the previous one. */
export const SKIP_WINDOW_MS = 1500;

export type TrackedEvent = Omit<EventRequest, "session_id">;

export type PlayTracker = {
  /** A result window started playing at `now` (ms). Returns the events to send, in order. */
  play: (windowId: string, queryId: string | null, now: number) => TrackedEvent[];
};

/**
 * - `play`: the first play of a card per query (replays and re-plays after a skip send nothing).
 * - `skip`: another card started less than SKIP_WINDOW_MS after this one started (sent once per start).
 */
export function createPlayTracker(): PlayTracker {
  const played = new Set<string>();
  let last: { windowId: string; queryId: string | null; at: number } | null = null;

  return {
    play(windowId, queryId, now) {
      const out: TrackedEvent[] = [];
      if (last && last.windowId !== windowId && now - last.at < SKIP_WINDOW_MS) {
        out.push({ action: "skip", window_id: last.windowId, query_id: last.queryId });
      }
      const key = `${queryId ?? ""}\u0000${windowId}`;
      if (!played.has(key)) {
        played.add(key);
        out.push({ action: "play", window_id: windowId, query_id: queryId });
      }
      last = { windowId, queryId, at: now };
      return out;
    },
  };
}

/** A preview transition is a "start" when an item becomes active that wasn't active (or wasn't this item) before. */
export function isPreviewStart(
  prev: { id: string | null; active: boolean },
  next: { id: string | null; active: boolean },
): boolean {
  return next.active && next.id !== null && (!prev.active || prev.id !== next.id);
}
