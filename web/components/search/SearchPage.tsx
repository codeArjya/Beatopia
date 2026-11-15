"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useChips } from "@/lib/api";
import { useDataMode } from "@/lib/api/useOffline";
import { useStopPreviewOnHide } from "@/lib/preview/PreviewProvider";
import { indexChips } from "@/lib/search/chips";
import { useSearchState } from "@/lib/search/useSearchState";

import { ChipTray } from "./ChipTray";
import { SearchBar } from "./SearchBar";
import { ResultList } from "./ResultList";
import { SearchDnd } from "./SearchDnd";
import { SearchShortcuts } from "./SearchShortcuts";

/** The search page body. Render inside <Suspense> (it reads the URL). */
export function SearchPage() {
  const { state, dispatch, request } = useSearchState();
  useStopPreviewOnHide();
  const chips = useChips();
  const { fixtures } = useDataMode();
  const index = useMemo(() => indexChips(chips.data?.categories ?? []), [chips.data]);

  const lastChipId = state.chips.at(-1);
  const lastChipLabel = lastChipId ? (index.get(lastChipId)?.label ?? lastChipId) : null;

  const toggle = (id: string) =>
    dispatch(state.chips.includes(id) ? { type: "remove", id } : { type: "add", id });

  return (
    <SearchDnd chips={state.chips} index={index} dispatch={dispatch}>
      <div className="mx-auto grid w-full max-w-7xl flex-1 gap-6 px-4 py-6 sm:px-6 md:grid-cols-[16rem_1fr]">
        <aside className="md:sticky md:top-20 md:max-h-[calc(100dvh-6rem)] md:self-start md:overflow-hidden">
          <ChipTray selected={state.chips} onToggle={toggle} className="md:max-h-[calc(100dvh-6rem)]" />
        </aside>

        <section aria-label="Search" className="min-w-0 space-y-4">
          {/* The hero above carries the page's <h1>. */}
          <h2 className="sr-only">Search samples</h2>
          <SearchBar state={state} index={index} dispatch={dispatch} />
          <div className="-mt-2 flex justify-end">
            <SearchShortcuts />
          </div>

          {request ? (
            <ResultList
              request={request}
              lastChipLabel={lastChipLabel}
              onRemoveLastChip={() => dispatch({ type: "removeLast" })}
            />
          ) : (
            <div className="space-y-3 py-16 text-center">
              <p className="text-title">Find your next sample</p>
              <p className="text-text-secondary">Type a sound, or stack chips from the tray.</p>
              {/* The fixture track only exists in fixture mode (build-time or ?offline=1). */}
              {fixtures && (
                <p className="text-caption text-text-tertiary">
                  <Link className="underline underline-offset-4 hover:text-foreground" href="/editor?track=jam_1532881&start=0&end=10.667&stem=mix">
                    Open the editor on a fixture
                  </Link>
                </p>
              )}
            </div>
          )}
        </section>
      </div>
    </SearchDnd>
  );
}

export function SearchPageSkeleton() {
  return (
    <div className="mx-auto grid w-full max-w-7xl flex-1 gap-6 px-4 py-6 sm:px-6 md:grid-cols-[16rem_1fr]">
      <div className="h-96 animate-pulse rounded-lg bg-skeleton" />
      <div className="h-11 animate-pulse rounded-lg bg-skeleton" />
    </div>
  );
}
