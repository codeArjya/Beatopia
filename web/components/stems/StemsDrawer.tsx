"use client";

import { ArrowRightIcon, RotateCwIcon, TriangleAlertIcon } from "lucide-react";
import Link from "next/link";

import { AppButton, AppSheet } from "@/components/adapters";
import { PlayButton } from "@/components/search/PlayButton";
import { editorHref } from "@/lib/links";
import { usePreviewPlayer } from "@/lib/preview/PreviewProvider";
import { STUCK_QUEUE_MS } from "@/lib/import/flow";
import { formatWindow } from "@/lib/search/results";
import { useSlow } from "@/lib/search/useSlow";
import { sortStems, stemPreviewItem, type StemsFlowStatus } from "@/lib/stems/flow";
import { useStemsFlow } from "@/lib/stems/useStemsFlow";
import type { Stem } from "@/lib/types/api";

export type StemsDrawerProps = {
  trackId: string;
  startS: number;
  endS: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Shown in the header; defaults to "Stems". */
  trackTitle?: string;
  /**
   * WS4: add the stem as a clip instead of navigating. Without it, "Use in editor" opens
   * `/editor?track=…&start=…&end=…&stem=…`.
   */
  onPick?: (stem: Stem) => void;
};

const STEM_LABEL: Record<Stem["stem"], string> = {
  drums: "Drums",
  bass: "Bass",
  vocals: "Vocals",
  other: "Other (keys, synths)",
  piano: "Piano",
  guitar: "Guitar",
  mix: "Full mix",
};

const STATUS_TEXT: Partial<Record<StemsFlowStatus, string>> = {
  requesting: "Asking for stems…",
  queued: "Queued for separation…",
  running: "Separating stems…",
};

/**
 * Right-hand sheet with one row per stem of a window. Stems that already exist show at once; otherwise a
 * separation job is polled with a progress bar. Each row plays that stem alone through the shared preview
 * player and can be sent to the editor. Radix handles Esc, the focus trap, and returning focus to the opener.
 */
export function StemsDrawer({ trackId, startS, endS, open, onOpenChange, trackTitle, onPick }: StemsDrawerProps) {
  const player = usePreviewPlayer();
  const flow = useStemsFlow(trackId, startS, endS, open);
  const stuck = useSlow(flow.status === "queued", `${trackId}:${startS}-${endS}`, STUCK_QUEUE_MS);

  const onOpen = (next: boolean) => {
    // Closing the drawer stops a stem preview (a card's own mix preview keeps playing).
    if (!next && player.getSnapshot().item?.id.startsWith("stem:")) player.stop();
    onOpenChange(next);
  };

  return (
    <AppSheet
      open={open}
      onOpenChange={onOpen}
      title={trackTitle ? `Stems: ${trackTitle}` : "Stems"}
      description={`Window ${formatWindow({ start_s: startS, end_s: endS })}. Play one part alone, or take it to the editor.`}
    >
      {(flow.status === "requesting" || flow.status === "queued" || flow.status === "running") && (
        <div className="space-y-2" role="status">
          <p className="text-sm text-muted-foreground">{STATUS_TEXT[flow.status]}</p>
          <ProgressBar value={flow.status === "requesting" ? null : flow.progress} />
          {flow.status !== "requesting" && (
            <p className="text-xs text-muted-foreground">Separation takes up to a minute. You can close this and come back.</p>
          )}
          {stuck && (
            <p className="text-sm text-warning">
              The separator hasn&apos;t started this yet; it may be busy or offline. We&apos;ll keep checking.
            </p>
          )}
        </div>
      )}

      {flow.status === "error" && (
        <div role="alert" className="space-y-3 rounded-lg border border-destructive/40 p-3 text-sm">
          <p className="flex items-start gap-2">
            <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
            <span>Couldn&apos;t get stems. {flow.error}</span>
          </p>
          <AppButton size="sm" variant="outline" onClick={flow.retry}>
            <RotateCwIcon className="size-3.5" aria-hidden />
            Retry
          </AppButton>
        </div>
      )}

      {flow.status === "ready" && flow.stems && (
        <ul aria-label="Stems" className="divide-y">
          {sortStems(flow.stems).map((stem) => (
            <StemRow
              key={`${stem.stem}:${stem.range_start_s}`}
              stem={stem}
              trackId={trackId}
              startS={startS}
              endS={endS}
              onPick={onPick}
              onLeave={() => onOpen(false)}
            />
          ))}
        </ul>
      )}
    </AppSheet>
  );
}

function StemRow({
  stem,
  trackId,
  startS,
  endS,
  onPick,
  onLeave,
}: {
  stem: Stem;
  trackId: string;
  startS: number;
  endS: number;
  onPick?: (stem: Stem) => void;
  onLeave: () => void;
}) {
  const player = usePreviewPlayer();
  const label = STEM_LABEL[stem.stem];
  const item = stemPreviewItem(stem, startS, endS);
  const useLabel = `Use ${label} in the editor`;

  return (
    <li className="flex items-center gap-3 py-2.5">
      <PlayButton item={item} title={`${label} stem`} />
      <span className="min-w-0 flex-1 truncate font-medium">{label}</span>
      {onPick ? (
        <AppButton
          size="sm"
          variant="ghost"
          aria-label={useLabel}
          onClick={() => {
            player.stop();
            onPick(stem);
          }}
        >
          Use in editor
          <ArrowRightIcon className="size-3.5" aria-hidden />
        </AppButton>
      ) : (
        <AppButton asChild size="sm" variant="ghost">
          <Link
            href={editorHref({ track: trackId, start: startS, end: endS, stem: stem.stem })}
            aria-label={useLabel}
            onClick={() => {
              player.stop();
              onLeave();
            }}
          >
            Use in editor
            <ArrowRightIcon className="size-3.5" aria-hidden />
          </Link>
        </AppButton>
      )}
    </li>
  );
}

/** `value` null = indeterminate (waiting for the first answer). */
function ProgressBar({ value }: { value: number | null }) {
  const pct = value == null ? null : Math.round(value * 100);
  return (
    <div
      role="progressbar"
      aria-label="Stem separation progress"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct ?? undefined}
      className="h-1.5 w-full overflow-hidden rounded-full bg-secondary"
    >
      <div
        className={pct == null ? "h-full w-1/3 animate-pulse rounded-full bg-primary/60" : "h-full rounded-full bg-primary transition-[width] duration-200"}
        style={pct == null ? undefined : { width: `${Math.max(pct, 3)}%` }}
      />
    </div>
  );
}
