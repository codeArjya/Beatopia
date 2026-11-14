"use client";

import { cn } from "cn";

import { AppButton, MonoStat } from "@/components/adapters";
import { ApiError, useSearch, type SearchParams } from "@/lib/api";
import { usePreviewPlayer, usePreviewStatus } from "@/lib/preview/PreviewProvider";
import type { Result } from "@/lib/types/api";

type SearchResultsProps = {
  /** Debounced request from useSearchState; never null here (the page shows the idle state instead). */
  request: SearchParams;
};

/**
 * Runs the search and renders its states. Previous results stay on screen (dimmed) while the next search loads.
 * Interim rows: T3.2 replaces them with ResultCard / ResultList (skeletons, empty state, fallback banner).
 */
export function SearchResults({ request }: SearchResultsProps) {
  const search = useSearch(request);
  const results = search.data?.results;
  const refreshing = search.isPlaceholderData || (search.isFetching && !search.isPending);

  const status = search.isPending
    ? "Searching…"
    : search.isError && !results
      ? "Search failed."
      : results
        ? `${results.length} ${results.length === 1 ? "result" : "results"}${refreshing ? ", updating…" : ""}`
        : "";

  return (
    <div className="space-y-3">
      <p aria-live="polite" className="text-sm text-muted-foreground">
        {status}
      </p>

      {search.isError && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-destructive/50 px-3 py-2 text-sm">
          <span className="flex-1">
            {search.error instanceof ApiError ? search.error.message : "Something went wrong."}
          </span>
          <AppButton size="sm" variant="outline" onClick={() => void search.refetch()}>
            Retry
          </AppButton>
        </div>
      )}

      {results && (
        <ol
          aria-busy={refreshing}
          className={cn("space-y-1.5 transition-opacity", refreshing && "opacity-60")}
        >
          {results.map((r) => (
            <li key={r.window_id} className="flex items-baseline gap-3 rounded-md border bg-card px-3 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate" title={r.track.title}>
                {r.track.title}
                {r.track.artist && <span className="text-muted-foreground"> · {r.track.artist}</span>}
              </span>
              <MonoStat label="BPM" value={r.track.bpm != null ? Math.round(r.track.bpm) : null} unit="bpm" />
              <MonoStat label="Bars" value={r.bars} unit="bars" />
              <InterimPlay result={r} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** Interim play toggle (T3.1); T3.2's ResultCard replaces it. */
function InterimPlay({ result: r }: { result: Result }) {
  const player = usePreviewPlayer();
  const status = usePreviewStatus(r.window_id);
  const item = { id: r.window_id, url: r.audio_url, start: r.start_s, end: r.end_s };
  return (
    <AppButton
      size="sm"
      variant="outline"
      onPointerEnter={() => player.warm(r.audio_url)}
      onClick={() => player.toggle(item)}
      aria-pressed={status === "playing" || status === "loading"}
    >
      {status === "playing" ? "Stop" : status === "loading" ? "…" : status === "error" ? "Retry" : "Play"}
    </AppButton>
  );
}
