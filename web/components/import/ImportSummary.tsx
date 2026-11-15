"use client";

import { ArrowRightIcon, RotateCcwIcon } from "lucide-react";
import Link from "next/link";

import { AppButton, AppCard, Attribution, LicenseBadge, MonoStat } from "@/components/adapters";
import { PlayButton } from "@/components/search/PlayButton";
import { importEditorLink } from "@/lib/import/flow";
import { editorHref } from "@/lib/links";
import { usePreviewPlayer } from "@/lib/preview/PreviewProvider";
import { formatTime, formatWindow } from "@/lib/search/results";
import type { TrackDetail } from "@/lib/types/api";

/** What the analysis found, a preview of the chosen window, and the editor hand-off. */
export function ImportSummary({ detail, onAnother }: { detail: TrackDetail; onAnother: () => void }) {
  const player = usePreviewPlayer();
  const t = detail.track;
  const link = importEditorLink(detail);
  const fromWindow = detail.windows.length > 0;
  const item = { id: `import:${t.id}:${link.start}-${link.end}`, url: detail.audio_url, start: link.start, end: link.end };

  return (
    <AppCard aria-labelledby="import-title" className="gap-4">
      <div className="flex items-start gap-3">
        <PlayButton item={item} title={t.title} className="mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Analysis done</p>
          <h2 id="import-title" className="truncate text-lg font-semibold" title={t.title}>
            {t.title}
          </h2>
          {t.artist && <p className="truncate text-sm text-muted-foreground">{t.artist}</p>}
        </div>
        <LicenseBadge license={t.license} attribution={t.attribution} />
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
        <Stat label="Length">
          <MonoStat label="Length" value={t.duration_s > 0 ? formatTime(t.duration_s) : null} />
        </Stat>
        <Stat label="Tempo">
          <MonoStat label="Tempo" value={t.bpm} unit="BPM" />
        </Stat>
        <Stat label="Key">
          <MonoStat label="Key" value={t.key} />
        </Stat>
        <Stat label="Loop windows">
          <MonoStat label="Loop windows" value={detail.windows.length} />
        </Stat>
      </dl>

      <p className="text-sm text-muted-foreground">
        {fromWindow ? "Best loop window" : "No loop windows found, so the editor opens on the first 8 bars"}:{" "}
        <span className="font-mono tabular-nums text-foreground">{formatWindow({ start_s: link.start, end_s: link.end })}</span>
      </p>
      <Attribution text={t.attribution} />

      <div className="flex flex-wrap gap-2">
        <AppButton asChild>
          <Link href={editorHref(link)} onClick={() => player.stop()}>
            Open in editor
            <ArrowRightIcon aria-hidden />
          </Link>
        </AppButton>
        <AppButton variant="outline" onClick={onAnother}>
          <RotateCcwIcon aria-hidden />
          Import another
        </AppButton>
      </div>
    </AppCard>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm [&_*]:text-sm">{children}</dd>
    </div>
  );
}
