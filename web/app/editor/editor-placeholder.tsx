"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";

import { api } from "@/lib/api/client";

export function EditorPlaceholder() {
  const params = useSearchParams();
  const trackId = params.get("track");
  const track = useQuery({
    queryKey: ["track", trackId],
    queryFn: () => api.getTrack(trackId as string),
    enabled: !!trackId,
  });

  if (!trackId) return <p className="text-muted-foreground">No track selected.</p>;
  if (track.isPending) return <p className="text-muted-foreground">Loading track…</p>;
  if (track.isError) return <p className="text-destructive">{track.error.message}</p>;

  const t = track.data.track;
  return (
    <div className="space-y-2">
      <p>
        <span className="font-medium">{t.title}</span> by {t.artist ?? "unknown"} ·{" "}
        <span className="font-mono">
          {t.bpm ?? "?"} BPM · {t.key ?? "?"}
        </span>
      </p>
      <p className="text-muted-foreground text-sm">
        Window {params.get("start")}–{params.get("end")} s, stem {params.get("stem") ?? "mix"} · {t.license}:{" "}
        {t.attribution}
      </p>
      <audio controls src={track.data.audio_url} className="w-full" />
    </div>
  );
}
