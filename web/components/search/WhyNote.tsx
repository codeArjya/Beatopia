"use client";

import { cn } from "cn";
import { RotateCwIcon, SparklesIcon } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { AppButton } from "@/components/adapters";
import { useWhy } from "@/lib/api";
import { usePreviewStatus } from "@/lib/preview/PreviewProvider";
import { shouldRequestWhy, whyView } from "@/lib/search/why";

/**
 * "Why this works as a sample". Collapsed to 2 lines with a More/Less toggle when it overflows. A cached note
 * (`Result.why`) shows with no request; a missing one is fetched on the first expand or the first play of the
 * card (the preview id is the window id), never on scroll.
 */
export function WhyNote({ windowId, cachedNote }: { windowId: string; cachedNote: string | null | undefined }) {
  const preview = usePreviewStatus(windowId);
  const [expanded, setExpanded] = useState(false);
  const [requested, setRequested] = useState(false);
  // Latch "requested" during render (no effect round-trip) the first time the card plays or expands.
  if (!requested && shouldRequestWhy(requested, expanded, preview)) setRequested(true);

  const why = useWhy(windowId, { cachedNote, enabled: requested });
  const note = why.data?.note;
  const view = whyView({ note, requested, isError: why.isError });

  return (
    <div className="min-w-0 text-sm break-words" aria-live="polite" aria-busy={view === "loading"}>
      {view === "prompt" && (
        <button
          type="button"
          aria-expanded={false}
          onClick={() => setExpanded(true)}
          className="inline-flex items-center gap-1.5 rounded text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          <SparklesIcon className="size-3.5 text-primary-strong" aria-hidden />
          Why this works as a sample
        </button>
      )}

      {view === "loading" && (
        <div className="space-y-1.5 py-0.5" role="status">
          <span className="sr-only">Loading why this works as a sample…</span>
          <div className="h-3.5 w-full animate-pulse rounded bg-skeleton" />
          <div className="h-3.5 w-2/3 animate-pulse rounded bg-skeleton" />
        </div>
      )}

      {view === "error" && (
        <p className="flex flex-wrap items-center gap-2 text-muted-foreground">
          Couldn&apos;t load the note.
          <AppButton size="sm" variant="ghost" className="h-7 px-2" onClick={() => void why.refetch()}>
            <RotateCwIcon className="size-3.5" aria-hidden />
            Retry
          </AppButton>
        </p>
      )}

      {view === "note" && note && <NoteText note={note} expanded={expanded} onToggle={() => setExpanded((v) => !v)} />}
    </div>
  );
}

function NoteText({ note, expanded, onToggle }: { note: string; expanded: boolean; onToggle: () => void }) {
  const id = useId();
  const ref = useRef<HTMLParagraphElement>(null);
  const [overflows, setOverflows] = useState(false);

  // Measure only while clamped: when expanded, scrollHeight === clientHeight and the toggle must stay.
  useEffect(() => {
    const el = ref.current;
    if (!el || expanded) return;
    const ro = new ResizeObserver(() => setOverflows(el.scrollHeight > el.clientHeight + 1));
    ro.observe(el);
    return () => ro.disconnect();
  }, [note, expanded]);

  return (
    <div className="flex min-w-0 flex-col items-start gap-0.5">
      <p id={id} ref={ref} className={cn("text-foreground/85", !expanded && "line-clamp-2")}>
        <span className="sr-only">Why this works as a sample: </span>
        {note}
      </p>
      {(expanded || overflows) && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={id}
          onClick={onToggle}
          className="rounded text-xs text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          {expanded ? "Less" : "More"}
        </button>
      )}
    </div>
  );
}
