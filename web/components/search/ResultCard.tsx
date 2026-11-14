"use client";

import { cn } from "cn";
import { LoaderCircleIcon, PlayIcon, SquareIcon, TriangleAlertIcon } from "lucide-react";
import { useId } from "react";

import { AppButton, AppCard, Attribution, LicenseBadge, MonoStat } from "@/components/adapters";
import { usePreviewPlayer, usePreviewStatus, type PreviewItem } from "@/lib/preview/PreviewProvider";
import { formatWindow, topTags } from "@/lib/search/results";
import type { Result } from "@/lib/types/api";

import { MiniWaveform } from "./MiniWaveform";

export function previewItemOf(r: Result): PreviewItem {
  return { id: r.window_id, url: r.audio_url, start: r.start_s, end: r.end_s };
}

/**
 * One search result: waveform slot, title/artist, BPM · key · bars, top tags, why note, license + attribution.
 * A focusable <article> labelled by its title. Space/Enter on the card (T3.4), Stems (T5.2) and
 * Open in editor (T3.4) come later; the waveform slot is a placeholder until T3.3.
 */
export function ResultCard({ result: r }: { result: Result }) {
  const titleId = useId();
  const player = usePreviewPlayer();
  const item = previewItemOf(r);
  const warm = () => player.warm(r.audio_url);
  const tags = topTags(r.tags);
  const fallbackSource = r.track.source === "freesound";

  return (
    <AppCard tabIndex={0} aria-labelledby={titleId} onPointerEnter={warm} onFocus={warm} className="min-w-0 flex-1 gap-2.5">
      <MiniWaveform item={item} />

      <div className="flex min-w-0 items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 id={titleId} className="truncate font-medium leading-snug" title={r.track.title}>
            {r.track.title}
          </h3>
          <p className="truncate text-sm text-muted-foreground" title={r.track.artist ?? undefined}>
            {r.track.artist ?? "Unknown artist"}
            {fallbackSource && <span className="text-xs"> · Freesound</span>}
          </p>
        </div>
        <PlayButton item={item} title={r.track.title} />
      </div>

      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1.5">
        <MonoStat label="Tempo" value={r.track.bpm != null ? Math.round(r.track.bpm) : null} unit="bpm" />
        <MonoStat label="Key" value={r.track.key} />
        <MonoStat label="Length" value={r.bars} unit={r.bars === 1 ? "bar" : "bars"} />
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          <span className="sr-only">Window: </span>
          {formatWindow(r)}
        </span>
        {tags.length > 0 && (
          <ul aria-label="Tags" className="flex min-w-0 flex-wrap gap-1">
            {tags.map((t) => (
              <li key={t} className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                {t}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* T4.1 replaces this with the collapsible, lazily fetched WhyNote. */}
      {r.why && <p className="line-clamp-2 text-sm text-foreground/85">{r.why}</p>}

      <div className="mt-auto flex min-w-0 items-center gap-2 pt-1">
        <LicenseBadge license={r.track.license} attribution={r.track.attribution} />
        <Attribution text={r.track.attribution} className="min-w-0 flex-1" />
      </div>
    </AppCard>
  );
}

function PlayButton({ item, title }: { item: PreviewItem; title: string }) {
  const player = usePreviewPlayer();
  const status = usePreviewStatus(item.id);
  const active = status === "playing" || status === "loading";
  const Icon =
    status === "playing" ? SquareIcon : status === "loading" ? LoaderCircleIcon : status === "error" ? TriangleAlertIcon : PlayIcon;
  const label =
    status === "error" ? `Preview failed, retry ${title}` : active ? `Stop preview of ${title}` : `Play preview of ${title}`;

  return (
    <AppButton
      size="icon"
      variant={active ? "default" : "outline"}
      className={cn("shrink-0 rounded-full", status === "error" && "border-destructive text-destructive")}
      aria-label={label}
      aria-pressed={active}
      title={status === "error" ? "Couldn't play this preview. Click to retry." : undefined}
      onClick={() => player.toggle(item)}
    >
      <Icon className={cn("size-4", status === "loading" && "animate-spin", status === "playing" && "fill-current")} aria-hidden />
    </AppButton>
  );
}

/** Same footprint as ResultCard, shown on the first load. */
export function ResultCardSkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-2.5 rounded-xl border bg-card p-4">
      <div className="h-12 animate-pulse rounded-md bg-muted/50" />
      <div className="flex items-start gap-3">
        <div className="flex-1 space-y-1.5">
          <div className="h-4 w-2/3 animate-pulse rounded bg-muted/60" />
          <div className="h-3.5 w-1/3 animate-pulse rounded bg-muted/50" />
        </div>
        <div className="size-9 animate-pulse rounded-full bg-muted/60" />
      </div>
      <div className="h-3.5 w-1/2 animate-pulse rounded bg-muted/50" />
      <div className="h-8 animate-pulse rounded bg-muted/40" />
      <div className="h-5 w-3/4 animate-pulse rounded bg-muted/40" />
    </div>
  );
}
