// Pure helpers for the result list: error classification, status text, card fields. No React, so they're unit-tested.
import { ApiError } from "@/lib/api";
import type { Result } from "@/lib/types/api";

/**
 * How a failed search is shown:
 * - "network": the API is unreachable → banner (later links to the ?offline=1 backup).
 * - "retryable": rate_limited / upstream_error / timeout → inline retry + a toast.
 * - "other": anything else → inline message + retry.
 */
export type SearchErrorKind = "network" | "retryable" | "other";

export function searchErrorKind(error: unknown): SearchErrorKind {
  if (!(error instanceof ApiError)) return "other";
  if (error.code === "network_error") return "network";
  if (error.code === "rate_limited" || error.code === "upstream_error" || error.code === "timeout") {
    return "retryable";
  }
  return "other";
}

export function searchErrorMessage(error: unknown): string {
  switch (searchErrorKind(error)) {
    case "network":
      return "Can't reach the Beatopia server. Check your connection.";
    case "retryable":
      if (error instanceof ApiError && error.code === "rate_limited") return "Too many searches at once. Give it a second.";
      if (error instanceof ApiError && error.code === "timeout") return "The search took too long. Try again.";
      return "The search service hiccuped.";
    default:
      return error instanceof Error && error.message ? error.message : "Something went wrong.";
  }
}

/** After this long without an answer, the status says so (real searches embed the query on a CPU VM). */
export const SLOW_SEARCH_MS = 3000;

/** The polite live-region text under the search bar. `slow` = the current request has run past SLOW_SEARCH_MS. */
export function resultsStatusText(opts: {
  pending: boolean;
  count: number | null;
  refreshing: boolean;
  failed: boolean;
  fallback: boolean;
  slow?: boolean;
}): string {
  if (opts.pending) return opts.slow ? "Still searching… the first search can take a few seconds." : "Searching…";
  if (opts.count === null) return opts.failed ? "Search failed." : "";
  const n = `${opts.count} ${opts.count === 1 ? "result" : "results"}`;
  const extra = [opts.count > 0 && opts.fallback ? "expanded to Freesound" : null, opts.refreshing ? (opts.slow ? "still updating…" : "updating…") : null];
  return [n, ...extra.filter(Boolean)].join(", ");
}

/** First `n` distinct, non-empty tags (the API orders them by relevance). */
export function topTags(tags: readonly string[], n = 3): string[] {
  const out: string[] = [];
  for (const t of tags) {
    const tag = t.trim();
    if (tag && !out.includes(tag)) out.push(tag);
    if (out.length === n) break;
  }
  return out;
}

/** "0:05.3–0:10.7": the window inside the track, for the card's caption and screen readers. */
export function formatWindow(r: Pick<Result, "start_s" | "end_s">): string {
  return `${formatTime(r.start_s)}–${formatTime(r.end_s)}`;
}

export function formatTime(s: number): string {
  const tenths = Number.isFinite(s) && s > 0 ? Math.round(s * 10) / 10 : 0; // round first: 59.96 → 1:00.0
  const m = Math.floor(tenths / 60);
  const rest = (tenths - m * 60).toFixed(1).padStart(4, "0");
  return `${m}:${rest}`;
}
