"use client";

import { ExternalLinkIcon, LayersIcon } from "lucide-react";
import Link from "next/link";
import { useId, useState, type KeyboardEvent } from "react";

import { AppButton, AppCard, Attribution, LicenseBadge, MonoStat } from "@/components/adapters";
import { editorHref } from "@/lib/links";
import { StemsDrawer } from "@/components/stems/StemsDrawer";
import { useSearchEvents } from "@/lib/events/SearchEvents";
import { usePreviewPlayer, type PreviewItem } from "@/lib/preview/PreviewProvider";
import { formatWindow, topTags } from "@/lib/search/results";
import type { Result } from "@/lib/types/api";

import { CoverArt } from "./CoverArt";
import { MiniWaveform } from "./MiniWaveform";
import { PlayButton } from "./PlayButton";
import { FlipTips } from "./FlipTips";
import { WhyNote } from "./WhyNote";

export function previewItemOf(r: Result): PreviewItem {
  return { id: r.window_id, url: r.audio_url, start: r.start_s, end: r.end_s };
}

export function editorHrefOf(r: Result): string {
  return editorHref({ track: r.track.id, start: r.start_s, end: r.end_s, stem: r.stem });
}

/**
 * One search result: mini waveform, title/artist, BPM · key · bars, top tags, why note, license + attribution,
 * Stems, Open in editor and Play. A focusable <article> labelled by its title; Space/Enter on the card itself
 * toggles the preview (keys inside its buttons/links, and in the portaled stems drawer, keep their own meaning).
 */
export function ResultCard({ result: r }: { result: Result }) {
  const titleId = useId();
  const player = usePreviewPlayer();
  const item = previewItemOf(r);
  const warm = () => player.warm(r.audio_url);
  const tags = topTags(r.tags);
  const fallbackSource = r.track.source === "freesound";
  const [stemsOpen, setStemsOpen] = useState(false);
  const events = useSearchEvents();

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.target !== e.currentTarget || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key !== " " && e.key !== "Enter") return;
    e.preventDefault(); // Space would scroll the page
    if (!e.repeat) player.toggle(item);
  };

  return (
    <AppCard
      tabIndex={0}
      aria-labelledby={titleId}
      aria-keyshortcuts="Space Enter s e j k"
      onPointerEnter={warm}
      onFocus={warm}
      onKeyDown={onKeyDown}
      className="@container min-w-0 flex-1 gap-2.5"
    >
      <MiniWaveform item={item} />

      <div className="flex min-w-0 items-start gap-3">
        <CoverArt result={r} />
        <div className="min-w-0 flex-1">
          <h3 id={titleId} className="truncate text-[16px] leading-6 font-semibold" title={r.track.title}>
            {r.track.title}
          </h3>
          <p className="truncate text-sm text-muted-foreground" title={r.track.artist ?? undefined}>
            {r.track.artist ?? "Unknown artist"}
            {fallbackSource && <span className="text-xs"> · Freesound</span>}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <AppButton
            size="sm"
            variant="ghost"
            className="text-muted-foreground hover:text-foreground"
            aria-label={`Stems of ${r.track.title}`}
            aria-haspopup="dialog"
            data-shortcut="stems"
            aria-expanded={stemsOpen}
            onClick={() => setStemsOpen(true)}
          >
            <LayersIcon className="size-4" aria-hidden />
            <span className="hidden @lg:inline">Stems</span>
          </AppButton>
          <AppButton asChild size="sm" variant="ghost" className="text-muted-foreground hover:text-foreground">
            <Link
              href={editorHrefOf(r)}
              data-shortcut="editor"
              aria-label={`Open ${r.track.title} in the editor`}
              // Hiding the page stops the preview too (useStopPreviewOnHide); stopping here is immediate.
              onClick={() => {
                player.stop();
                events.pick(r.window_id);
              }}
            >
              <ExternalLinkIcon className="size-4" aria-hidden />
              <span className="hidden @lg:inline">Open in editor</span>
            </Link>
          </AppButton>
          <PlayButton item={item} title={r.track.title} />
        </div>
      </div>

      <StemsDrawer
        trackId={r.track.id}
        trackTitle={r.track.title}
        startS={r.start_s}
        endS={r.end_s}
        open={stemsOpen}
        onOpenChange={setStemsOpen}
        onUse={() => events.pick(r.window_id)}
      />

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
              <li key={t} title={t} className="max-w-48 truncate rounded-[6px] bg-secondary px-2 py-0.5 text-xs text-text-secondary">
                {t}
              </li>
            ))}
          </ul>
        )}
      </div>

      <WhyNote windowId={r.window_id} cachedNote={r.why} />
      <FlipTips result={r} />

      <div className="mt-auto flex min-w-0 items-center gap-2 pt-1">
        <LicenseBadge license={r.track.license} attribution={r.track.attribution} />
        <Attribution text={r.track.attribution} className="min-w-0 flex-1" />
      </div>
    </AppCard>
  );
}

/** Same footprint as ResultCard, shown on the first load. */
export function ResultCardSkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-2.5 rounded-lg border bg-card p-4">
      <div className="h-12 animate-pulse rounded-md bg-skeleton" />
      <div className="flex items-start gap-3">
        <div className="flex-1 space-y-1.5">
          <div className="h-4 w-2/3 animate-pulse rounded bg-skeleton" />
          <div className="h-3.5 w-1/3 animate-pulse rounded bg-skeleton" />
        </div>
        <div className="size-9 animate-pulse rounded-full bg-skeleton" />
      </div>
      <div className="h-3.5 w-1/2 animate-pulse rounded bg-skeleton" />
      <div className="h-8 animate-pulse rounded bg-skeleton" />
      <div className="h-5 w-3/4 animate-pulse rounded bg-skeleton" />
    </div>
  );
}
