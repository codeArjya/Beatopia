"use client";

import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import Regions from "wavesurfer.js/dist/plugins/regions.esm.js";
import Timeline from "wavesurfer.js/dist/plugins/timeline.esm.js";
import type { PcmBuffer } from "@/lib/audio/types";
import { duration } from "@/lib/audio/pcm";

interface Props {
  pcm: PcmBuffer;
  bpm: number | null;
  selection: [number, number];
  cursor: number;
  onSelect: (range: [number, number]) => void;
  onSeek: (time: number) => void;
}
export function Waveform({ pcm, bpm, selection, cursor, onSelect, onSeek }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const wave = useRef<WaveSurfer | null>(null);
  const regions = useRef<Regions | null>(null);
  const callbacks = useRef({ onSelect, onSeek });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { callbacks.current = { onSelect, onSeek }; }, [onSelect, onSeek]);
  useEffect(() => {
    if (!container.current) return;
    const regionPlugin = Regions.create();
    const timeline = Timeline.create(bpm ? {
      timeInterval: 60 / bpm, primaryLabelSpacing: 4,
      formatTimeCallback: (time) => `${Math.floor(time * bpm / 240) + 1}`,
    } : {});
    const ws = WaveSurfer.create({
      container: container.current, height: 160, waveColor: "#64748b", progressColor: "#2563eb",
      cursorColor: "#e11d48", peaks: [...pcm.channels], duration: duration(pcm),
      plugins: [regionPlugin, timeline], interact: true,
    });
    wave.current = ws;
    regions.current = regionPlugin;
    let internal = false;
    const offReady = ws.on("ready", () => {
      internal = true;
      regionPlugin.addRegion({ id: "selection", start: 0, end: duration(pcm), color: "rgba(37,99,235,.13)", drag: true, resize: true });
      internal = false;
    });
    const update = (region: ReturnType<Regions["addRegion"]>) => {
      if (internal || region.start >= region.end) return;
      internal = true;
      regionPlugin.getRegions().filter((item) => item !== region).forEach((item) => item.remove());
      region.setOptions({ id: "selection" });
      internal = false;
      callbacks.current.onSelect([region.start, region.end]);
    };
    const offCreate = regionPlugin.on("region-created", update);
    const offUpdate = regionPlugin.on("region-updated", update);
    const offSeek = ws.on("interaction", (time) => callbacks.current.onSeek(time));
    const offError = ws.on("error", (event) => setError(event.message));
    const disableDrag = regionPlugin.enableDragSelection({ color: "rgba(37,99,235,.13)" });
    return () => {
      disableDrag(); offReady(); offCreate(); offUpdate(); offSeek(); offError();
      ws.destroy(); wave.current = null; regions.current = null;
    };
  }, [pcm, bpm]);
  useEffect(() => {
    const region = regions.current?.getRegions().find((item) => item.id === "selection");
    if (region) region.setOptions({ start: selection[0], end: selection[1] });
  }, [selection]);
  useEffect(() => { wave.current?.setTime(Math.min(cursor, duration(pcm))); }, [cursor, pcm]);
  return <div>
    <div ref={container} aria-label="Active clip waveform" />
    <p className="text-muted-foreground text-xs">{bpm ? "Timeline: bars (4/4)" : "Timeline: seconds"}. Drag the selection edges or enter clip-relative seconds below.</p>
    {error && <p role="alert">Waveform: {error}</p>}
  </div>;
}
