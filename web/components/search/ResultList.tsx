"use client";

import { cn } from "cn";
import { GlobeIcon, SearchXIcon, WifiOffIcon } from "lucide-react";
import { useEffect } from "react";
import { toast } from "sonner";

import { AppButton } from "@/components/adapters";
import { useSearch, type SearchParams } from "@/lib/api";
import { resultsStatusText, searchErrorKind, searchErrorMessage } from "@/lib/search/results";

import { ResultCard, ResultCardSkeleton } from "./ResultCard";

type ResultListProps = {
  /** Debounced request from useSearchState; never null here (the page shows the idle state instead). */
  request: SearchParams;
  /** Label of the last stacked chip, for the empty state's one-click "Remove …"; null when no chips are stacked. */
  lastChipLabel: string | null;
  onRemoveLastChip: () => void;
};

/**
 * Runs the search and renders every state: skeletons (first load), dimmed previous results (refetch),
 * empty state, "Expanded to Freesound" banner, errors (network banner / retryable toast / inline), and the count.
 */
export function ResultList({ request, lastChipLabel, onRemoveLastChip }: ResultListProps) {
  const search = useSearch(request);
  const data = search.data;
  const results = data?.results ?? null;
  const refreshing = search.isPlaceholderData || (search.isFetching && !search.isPending);
  const errorKind = search.isError ? searchErrorKind(search.error) : null;
  const retry = () => void search.refetch();

  // rate_limited / upstream_error also get a toast, once per failure (errorUpdatedAt changes per failure).
  const { errorUpdatedAt, error } = search;
  useEffect(() => {
    if (errorUpdatedAt && searchErrorKind(error) === "retryable") {
      toast.error(searchErrorMessage(error), { id: "search-error" });
    }
  }, [errorUpdatedAt, error]);

  const status = resultsStatusText({
    pending: search.isPending,
    count: results ? results.length : null,
    refreshing,
    failed: search.isError,
    fallback: data?.fallback_used === true,
  });

  return (
    <div className="space-y-3">
      <p aria-live="polite" className="text-sm text-muted-foreground">
        {status}
      </p>

      {errorKind === "network" && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm">
          <WifiOffIcon className="size-4 shrink-0 text-destructive" aria-hidden />
          <span className="flex-1">{searchErrorMessage(search.error)}</span>
          <AppButton size="sm" variant="outline" onClick={retry}>
            Retry
          </AppButton>
        </div>
      )}
      {(errorKind === "retryable" || errorKind === "other") && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-destructive/50 px-3 py-2 text-sm">
          <span className="flex-1">{searchErrorMessage(search.error)}</span>
          <AppButton size="sm" variant="outline" onClick={retry}>
            Retry
          </AppButton>
        </div>
      )}

      {data?.fallback_used && results && results.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-sm">
          <GlobeIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <p>
            <span className="font-medium">Expanded to Freesound.</span>{" "}
            <span className="text-muted-foreground">Few matches in the library, so these include Freesound sounds.</span>
          </p>
        </div>
      )}

      {search.isPending && (
        <ul aria-hidden className="grid gap-3 xl:grid-cols-2">
          {Array.from({ length: request.limit }, (_, i) => (
            <li key={i}>
              <ResultCardSkeleton />
            </li>
          ))}
        </ul>
      )}

      {results && results.length === 0 && (
        <EmptyState
          lastChipLabel={lastChipLabel}
          onRemoveLastChip={onRemoveLastChip}
          refreshing={refreshing}
          fallback={data?.fallback_used === true}
        />
      )}

      {results && results.length > 0 && (
        <ol
          aria-label="Results"
          aria-busy={refreshing}
          className={cn("grid gap-3 transition-opacity xl:grid-cols-2", refreshing && "opacity-60")}
        >
          {results.map((r) => (
            <li key={r.window_id} className="flex min-w-0">
              <ResultCard result={r} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function EmptyState({
  lastChipLabel,
  onRemoveLastChip,
  refreshing,
  fallback,
}: {
  lastChipLabel: string | null;
  onRemoveLastChip: () => void;
  refreshing: boolean;
  fallback: boolean;
}) {
  return (
    <div className={cn("flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center", refreshing && "opacity-60")}>
      <SearchXIcon className="size-8 text-muted-foreground" aria-hidden />
      <div className="space-y-1">
        <p className="font-medium">{lastChipLabel ? "No matches, try fewer chips" : "No matches, try different words"}</p>
        <p className="text-sm text-muted-foreground">
          {fallback ? "Even Freesound came up empty for this one." : "Nothing in the library matches all of that."}
        </p>
      </div>
      {lastChipLabel && (
        <AppButton size="sm" variant="outline" onClick={onRemoveLastChip}>
          Remove last chip ({lastChipLabel})
        </AppButton>
      )}
    </div>
  );
}
