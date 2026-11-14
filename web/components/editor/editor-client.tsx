"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useStore } from "zustand";
import { api, USE_FIXTURES } from "@/lib/api/client";
import type { Op } from "@/lib/types/api";
import { loadSource } from "@/lib/audio/decode";
import { parseEntry, resolveEntry } from "@/lib/audio/entry";
import { sourceKey } from "@/lib/audio/evaluate";
import { renderOffline } from "@/lib/audio/native-offline";
import { duration } from "@/lib/audio/pcm";
import { occurrenceAt, PlaybackController } from "@/lib/audio/playback";
import { encodeWav, exportFilename } from "@/lib/audio/wav";
import { createEditorStore } from "@/stores/editor";
import { Button } from "@/components/ui/button";
import { Toolbar } from "./toolbar";
import { Waveform } from "./waveform";

export function EditorClient() {
  const params = useSearchParams();
  const parsed = useMemo(() => {
    try { return { entry: parseEntry(params), error: null }; }
    catch (error) { return { entry: null, error: (error as Error).message }; }
  }, [params]);
  const [store] = useState(() => createEditorStore(renderOffline));
  const editor = useStore(store);
  const transport = useRef<PlaybackController | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState<{ status: string; error?: string }>({ status: "loading" });
  const [clock, setClock] = useState({ position: 0, playing: false });
  const [loop, setLoop] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const track = useQuery({ queryKey: ["track", parsed.entry?.trackId],
    queryFn: () => api.getTrack(parsed.entry!.trackId), enabled: !!parsed.entry });

  useEffect(() => {
    const player = new PlaybackController();
    transport.current = player;
    let frame = 0;
    const tick = () => {
      const state = store.getState();
      const occurrence = player.playing && state.current && occurrenceAt(state.current.evaluation, player.position);
      if (occurrence && occurrence.id !== state.active) state.select(occurrence.id);
      setClock((previous) => previous.position === player.position && previous.playing === player.playing
        ? previous : { position: player.position, playing: player.playing });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    // Stops synchronously when a render starts, including edits initiated elsewhere.
    const unsubscribe = store.subscribe((state, previous) => {
      if (state.revision !== previous.revision) player.seek(0);
    });
    return () => { cancelAnimationFrame(frame); unsubscribe(); player.dispose(); transport.current = null; store.getState().reset(); };
  }, [store]);

  useEffect(() => {
    const controller = new AbortController();
    store.getState().reset();
    if (!parsed.entry || !track.data) return () => controller.abort();
    const entry = parsed.entry;
    const detail = track.data;
    const run = async () => {
      setLoad({ status: "loading" });
      try {
        const resolved = resolveEntry(entry, detail);
        const pcm = await loadSource(resolved.source, resolved.origin, controller.signal);
        if (controller.signal.aborted) return;
        await store.getState().initialize({ bpm: detail.track.bpm, clips: [{ id: "c1", source: resolved.source }], ops: [], arrangement: [] },
          new Map([[sourceKey(resolved.source), { pcm, origin: entry.start, beatTimes: detail.beat_times, bpm: detail.track.bpm ?? null }]]));
        if (!store.getState().current && !controller.signal.aborted) throw new Error(store.getState().error ?? "Audio could not be loaded.");
        if (!controller.signal.aborted) setLoad({ status: "ready" });
      } catch (error) {
        if (!controller.signal.aborted) setLoad({ status: "error", error: (error as Error).message });
      }
    };
    void run();
    return () => { controller.abort(); store.getState().reset(); };
  }, [parsed.entry, track.data, attempt, store]);

  const retry = () => { if (track.isError) void track.refetch(); setAttempt((value) => value + 1); };
  const stop = () => transport.current?.stop();
  const apply = (ops: Op[]) => { stop(); setNotice(null); void editor.apply(ops); };
  const current = editor.current;
  const active = editor.active && current?.evaluation.clips.get(editor.active);
  const selection = editor.selection;
  const seek = (time: number) => {
    if (!current || !editor.active) return;
    let offset = 0;
    for (const id of current.evaluation.order) {
      if (id === editor.active) break;
      offset += duration(current.evaluation.clips.get(id)!.pcm);
    }
    const position = offset + time;
    if (transport.current?.playing) void transport.current.play(current.evaluation.rendered, position, loop).catch((error: Error) => setNotice(error.message));
    else transport.current?.seek(position);
    setClock({ position, playing: transport.current?.playing ?? false });
  };
  const play = () => {
    if (!current) return;
    if (transport.current?.playing) { stop(); return; }
    void transport.current?.play(current.evaluation.rendered, clock.position, loop).catch((error: Error) => setNotice(error.message));
  };
  const download = () => {
    if (!current || !track.data || !parsed.entry) return;
    const pcm = current.evaluation.rendered;
    const filename = exportFilename(track.data.track);
    const url = URL.createObjectURL(new Blob([encodeWav(pcm)], { type: "audio/wav" }));
    const link = document.createElement("a");
    link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(`Downloaded ${filename} · 44100 Hz · 16-bit PCM · ${pcm.channels.length} channels · ${pcm.channels[0].length} frames`);
    const windowId = resolveEntry(parsed.entry, track.data).windowId;
    if (windowId) {
      try {
        const sessionId = localStorage.getItem("session_id") ?? crypto.randomUUID();
        localStorage.setItem("session_id", sessionId);
        void api.postEvent({ session_id: sessionId, window_id: windowId, action: "export" }).catch(() => setNotice((value) => `${value} · Export telemetry unavailable.`));
      } catch { /* Browser storage availability must not invalidate a download. */ }
    }
  };
  let activeOffset = 0;
  if (current && editor.active) {
    for (const id of current.evaluation.order) {
      if (id === editor.active) break;
      activeOffset += duration(current.evaluation.clips.get(id)!.pcm);
    }
  }

  if (parsed.error) return <div className="space-y-3"><p role="alert">{parsed.error}</p>
    <a className="underline" href="/editor?track=jam_1532881&start=0&end=16&stem=mix">Open jam_1532881 fixture (16 s)</a></div>;
  if (track.isError) return <div><p role="alert">{track.error.message}</p><Button onClick={retry}>Retry track</Button></div>;
  if (!track.data) return <p role="status">Loading track metadata…</p>;
  const metadata = track.data.track;
  return <div className="space-y-6">
    <header className="space-y-1">
      <h2 className="text-xl font-medium">{metadata.title}</h2>
      <p>{metadata.artist ?? "Unknown artist"} · {metadata.bpm ?? "Unknown"} BPM · {metadata.key ?? "Unknown key"}</p>
      <p className="text-muted-foreground text-sm">{parsed.entry!.start}–{parsed.entry!.end} s · {parsed.entry!.stem} · {USE_FIXTURES ? "Fixture library" : "Live library"}</p>
      <p className="text-sm">{metadata.license} · {metadata.attribution}</p>
    </header>
    {load.status === "loading" && <p role="status">Loading and decoding audio…</p>}
    {load.error && <div><p role="alert">{load.error}</p><Button onClick={retry}>Retry audio</Button><p className="text-sm">Fixture fallback: start the web server with NEXT_PUBLIC_USE_FIXTURES=1 and open the fixture link.</p></div>}
    {editor.error && <p className="text-destructive" role="alert">{editor.error}</p>}
    {current && active && selection && editor.active && <>
      <div className="flex flex-wrap gap-2" aria-label="Choose active clip">
        {current.evaluation.leaves.map((id) => <Button key={id} variant={editor.active === id ? "default" : "outline"} onClick={() => { stop(); editor.select(id); }}>
          {id} · {duration(current.evaluation.clips.get(id)!.pcm).toFixed(3)} s
        </Button>)}
      </div>
      <section className="rounded-xl border p-4" aria-label="Waveform and selection">
        <Waveform pcm={active.pcm} bpm={active.tempoBpm} selection={selection}
          cursor={Math.max(0, Math.min(duration(active.pcm), clock.position - activeOffset))}
          onSelect={editor.setSelection} onSeek={seek} />
      </section>
      <Toolbar active={editor.active} selection={selection} length={duration(active.pcm)} hasBeats={active.bpm != null && active.beatTimes.length > 0}
        bpm={active.bpm} disabled={editor.pending} canUndo={editor.past.length > 0} canRedo={editor.future.length > 0}
        onSelect={editor.setSelection} onApply={apply} onUndo={() => { stop(); editor.undo(); }} onRedo={() => { stop(); editor.redo(); }} />
      <div className="flex flex-wrap items-center gap-3 border-t pt-4">
        <Button disabled={editor.pending} onClick={play}>{clock.playing ? "Stop" : "Play"}</Button>
        <Button variant="outline" onClick={() => seek(selection[0])}>Seek to selection</Button>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={loop} onChange={(event) => { setLoop(event.target.checked); transport.current?.setLoop(event.target.checked); }} />Loop playback</label>
        <output className="font-mono text-sm">{clock.position.toFixed(2)} / {duration(current.evaluation.rendered).toFixed(2)} s</output>
        <Button disabled={editor.pending} onClick={download}>Download WAV</Button>
      </div>
      <p className="text-muted-foreground text-sm">{current.wire.ops.length} edits · {current.evaluation.rendered.channels[0].length} frames · {current.evaluation.rendered.channels.length} channels · WAV: 44.1 kHz / 16-bit</p>
      {editor.pending && <p role="status">Rendering…</p>}
    </>}
    {notice && <p role="status" className="break-words text-sm">{notice}</p>}
  </div>;
}
