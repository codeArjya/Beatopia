"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useChips } from "@/lib/api";
import { indexChips } from "@/lib/search/chips";
import { useSearchState } from "@/lib/search/useSearchState";

import { ChipTray } from "./ChipTray";
import { SearchBar } from "./SearchBar";
import { SearchDnd } from "./SearchDnd";

/** The search page body. Render inside <Suspense> (it reads the URL). */
export function SearchPage() {
  const { state, dispatch, request } = useSearchState();
  const chips = useChips();
  const index = useMemo(() => indexChips(chips.data?.categories ?? []), [chips.data]);

  const toggle = (id: string) =>
    dispatch(state.chips.includes(id) ? { type: "remove", id } : { type: "add", id });

  return (
    <SearchDnd chips={state.chips} index={index} dispatch={dispatch}>
    <div className="mx-auto grid w-full max-w-7xl flex-1 gap-6 px-4 py-6 sm:px-6 md:grid-cols-[16rem_1fr]">
      <aside className="md:sticky md:top-20 md:max-h-[calc(100dvh-6rem)] md:self-start md:overflow-hidden">
        <ChipTray selected={state.chips} onToggle={toggle} className="md:max-h-[calc(100dvh-6rem)]" />
      </aside>

      <section aria-label="Search" className="min-w-0 space-y-4">
        <h1 className="sr-only">Search samples</h1>
        <SearchBar state={state} index={index} dispatch={dispatch} />

        {/* Placeholder until results land (T2.4 / T3.2). */}
        {request ? (
          <p className="text-sm text-muted-foreground">
            Ready to search for{" "}
            <span className="font-mono text-foreground">
              {[request.text && `"${request.text}"`, ...request.chips.map((id) => index.get(id)?.label ?? id)]
                .filter(Boolean)
                .join(" + ")}
            </span>
            .
          </p>
        ) : (
          <div className="space-y-2 py-12 text-center">
            <p className="text-lg font-medium">Find your next sample</p>
            <p className="text-sm text-muted-foreground">Type a sound, or stack chips from the tray.</p>
            <p className="text-xs text-muted-foreground">
              <Link className="underline underline-offset-4 hover:text-foreground" href="/editor?track=jam_1532881&start=0&end=10.667&stem=mix">
                Open the editor on a fixture
              </Link>
            </p>
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
      <div className="h-96 animate-pulse rounded-lg bg-muted/50" />
      <div className="h-11 animate-pulse rounded-lg bg-muted/50" />
    </div>
  );
}
