"use client";

import { cn } from "cn";
import { ChevronDownIcon, WandSparklesIcon } from "lucide-react";
import { useId, useMemo, useState } from "react";

import { useWhy } from "@/lib/api";
import { flipTips } from "@/lib/search/flip";
import type { Result } from "@/lib/types/api";

/**
 * "Flip this sample": a collapsed list of ideas drawn from the why note plus the result's tempo, key, bars and
 * stem. Reads the note from the why cache only (WhyNote decides when to fetch), so it appears once a note exists.
 */
export function FlipTips({ result: r }: { result: Result }) {
  const why = useWhy(r.window_id, { cachedNote: r.why, enabled: false });
  const note = why.data?.note;
  const tips = useMemo(() => (note ? flipTips(note, r) : []), [note, r]);
  const [open, setOpen] = useState(false);
  const listId = useId();
  if (tips.length === 0) return null;

  return (
    <div className="min-w-0 text-sm">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-full py-0.5 text-text-secondary outline-none hover:text-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        <WandSparklesIcon className="size-3.5 text-primary-strong" aria-hidden />
        Flip this sample
        <ChevronDownIcon className={cn("size-3.5 transition-transform duration-(--dur-hover)", !open && "-rotate-90")} aria-hidden />
      </button>
      <ol id={listId} hidden={!open} className="mt-1.5 space-y-1.5 border-l-2 border-primary/50 pl-3">
        {tips.map((t) => (
          <li key={t.kind + t.text} className="text-foreground/90">
            {t.text}
          </li>
        ))}
      </ol>
    </div>
  );
}
