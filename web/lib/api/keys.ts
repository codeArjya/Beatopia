// Every TanStack Query key in the app. session_id is never part of a key.
import type { StemsRequest } from "@/lib/types/api";

export type SearchParams = { text: string | null; chips: string[]; limit: number };

export const keys = {
  health: ["health"] as const,
  chips: ["chips"] as const,
  search: (p: SearchParams | null) => ["search", p] as const,
  track: (id: string | null) => ["track", id] as const,
  stems: (trackId: string, r: StemsRequest) =>
    ["stems", trackId, r.start_s, r.end_s, r.model ?? "htdemucs"] as const,
  job: (id: string | null) => ["job", id] as const,
  why: (windowId: string) => ["why", windowId] as const,
  peaks: (url: string, start: number, end: number) => ["peaks", url, start, end] as const,
};
