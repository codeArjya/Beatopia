"use client";

import { useEffect, useRef, useState } from "react";
import type { TrackDetail } from "@/lib/types/api";
import { api } from "@/lib/api/client";
import { runBrowserChecks } from "@/lib/audio/browser-checks";
import { runHeroChecks } from "@/lib/audio/hero-checks";
import { PlaybackController } from "@/lib/audio/playback";
import { encodeWav, exportFilename } from "@/lib/audio/wav";
import type { PcmBuffer } from "@/lib/audio/types";

export function AudioChecks({ liveDetail }: { liveDetail?: TrackDetail }) {
  const [lines, setLines] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [golden, setGolden] = useState<PcmBuffer | null>(null);
  const player = useRef<PlaybackController | null>(null);
  useEffect(() => { player.current = new PlaybackController(); return () => player.current?.dispose(); }, []);
  const report = (line: string) => setLines((previous) => [...previous, line]);
  const run = async () => {
    setPending(true); setLines([]); setGolden(null);
    player.current?.stop();
    try {
      if (liveDetail) setGolden(await runHeroChecks(liveDetail, report));
      else {
        const detail: TrackDetail = await api.getTrack("jam_1532881");
        setGolden(await runBrowserChecks(detail, report));
      }
      report("ALL AUTOMATED BROWSER CHECKS PASSED");
    } catch (error) { report(`FAIL: ${(error as Error).message}`); }
    finally { setPending(false); }
  };
  return <main className="space-y-4 p-8">
    <h1>WS4 development audio checks</h1>
    <p>{liveDetail ? "Live public hero audio with a database metadata snapshot. This tests storage/engine/WAV, not the production API or editor UI." : "Synthetic fixture checks. These measurements do not replace listening or the editor UI checklist."}</p>
    {liveDetail && <p>{liveDetail.track.title} · {liveDetail.track.license} · {liveDetail.track.attribution}</p>}
    <a className="block underline" href={liveDetail ? "/editor/audio-checks" : "/editor/live-audio-checks"}>{liveDetail ? "Open fixture checks" : "Open live hero storage checks"}</a>
    {liveDetail && <a className="block underline" href="/editor/live-editor-checks?track=jam_1047157&start=5&end=15&stem=mix">Open this real hero in the development editor</a>}
    <button className="rounded border p-2" disabled={pending} onClick={() => void run()}>{pending ? "Running checks…" : "Run audio checks"}</button>
    <pre className="whitespace-pre-wrap" role="status">{lines.join("\n")}</pre>
    {golden && <div className="flex gap-4">
      <button onClick={() => void player.current?.play(golden, 0, false).catch((error: Error) => report(error.message))}>Preview golden WAV</button>
      <button onClick={() => player.current?.stop()}>Stop preview</button>
      <button onClick={() => {
        const url = URL.createObjectURL(new Blob([encodeWav(golden)], { type: "audio/wav" }));
        const link = document.createElement("a"); link.href = url; link.download = liveDetail ? exportFilename(liveDetail.track) : "beatopia-ws4-browser-golden.wav"; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }}>Download golden WAV</button>
    </div>}
  </main>;
}
