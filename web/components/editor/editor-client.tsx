"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useStore } from "zustand";
import { api, USE_FIXTURES } from "@/lib/api/client";
import type { Op, TrackDetail } from "@/lib/types/api";
import { loadSource } from "@/lib/audio/decode";
import { parseEntry, resolveEntry } from "@/lib/audio/entry";
import { sourceKey } from "@/lib/audio/evaluate";
import { loadLocalFile, loadStem, type LoadedSource } from "@/lib/audio/source-import";
import { ObjectUrls } from "@/lib/audio/object-urls";
import { renderOffline } from "@/lib/audio/native-offline";
import { duration } from "@/lib/audio/pcm";
import { occurrenceAt, PlaybackController } from "@/lib/audio/playback";
import { encodeWav, exportFilename } from "@/lib/audio/wav";
import { editorShortcut } from "@/lib/audio/editor-actions";
import { createEditorStore } from "@/stores/editor";
import { Button } from "@/components/ui/button";
import { Toolbar } from "./toolbar";
import { Waveform } from "./waveform";
import { ArrangementLane } from "./arrangement-lane";
import { HistoryPanel } from "./history-panel";
import { LocalFileDrop } from "./local-file-drop";
import { StemsDrawer } from "./stems-drawer";

export function EditorClient({ acceptanceDetail }: { acceptanceDetail?: TrackDetail } = {}) {
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
  const [selectedOccurrence, setSelectedOccurrence] = useState(0);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const importController = useRef<AbortController | null>(null);
  const [downloadUrls] = useState(() => new ObjectUrls());
  // Development-only metadata injection keeps real storage/UI checks independent of WS2.
  // Use an isolated cache key so a snapshot never seeds the product's track cache.
  const acceptance = process.env.NODE_ENV === "development" && acceptanceDetail?.track.id === parsed.entry?.trackId ? acceptanceDetail : undefined;
  const track = useQuery({ queryKey: ["track", parsed.entry?.trackId, ...(acceptance ? ["acceptance-snapshot", acceptance.audio_url, acceptance.track.bpm, acceptance.beat_times.length] : [])],
    queryFn: () => acceptance ? Promise.resolve(acceptance) : api.getTrack(parsed.entry!.trackId), enabled: !!parsed.entry,
    staleTime: Infinity, refetchOnWindowFocus: false, refetchOnReconnect: false });

  useEffect(() => {
    const player = new PlaybackController();
    transport.current = player;
    let frame = 0;
    const tick = () => {
      const state = store.getState();
      const occurrence = player.playing && state.current && occurrenceAt(state.current.evaluation, player.position);
      if (occurrence && occurrence.id !== state.active) state.select(occurrence.id);
      if (occurrence) setSelectedOccurrence((previous) => previous === occurrence.index ? previous : occurrence.index);
      setClock((previous) => previous.position === player.position && previous.playing === player.playing
        ? previous : { position: player.position, playing: player.playing });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    // Stops synchronously when a render starts, including edits initiated elsewhere.
    const unsubscribe = store.subscribe((state, previous) => {
      if (state.revision !== previous.revision) player.seek(0);
    });
    return () => { cancelAnimationFrame(frame); unsubscribe(); player.dispose(); transport.current = null;
      importController.current?.abort(); downloadUrls.dispose(); store.getState().reset(); };
  }, [store, downloadUrls]);

  useEffect(() => {
    const controller = new AbortController();
    importController.current?.abort();
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
          new Map([[sourceKey(resolved.source), { pcm, origin: entry.start, beatTimes: detail.beat_times, bpm: detail.track.bpm ?? null, metadata: detail.track }]]));
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
  const importSource = async (loader: (signal: AbortSignal) => Promise<LoadedSource>): Promise<boolean> => {
    if (importController.current && !importController.current.signal.aborted) return false;
    const controller = new AbortController();
    importController.current = controller;
    const revision = store.getState().revision;
    setImporting(true); setImportError(null); stop();
    try {
      const { source, asset } = await loader(controller.signal);
      controller.signal.throwIfAborted();
      const added = await store.getState().addSource(source, asset, revision);
      if (!added && !controller.signal.aborted) throw new Error(store.getState().error ?? "The editor changed while decoding. Add the source again.");
      if (added && !controller.signal.aborted) {
        const order = store.getState().current!.evaluation.order;
        setSelectedOccurrence(order.length - 1);
        transport.current?.seek(0);
        setNotice(`Added ${asset.metadata?.title ?? source.stem ?? "audio"}. Undo removes this source.`);
      }
      return added;
    } catch (error) {
      if (!controller.signal.aborted) setImportError((error as Error).message);
      return false;
    } finally {
      if (importController.current === controller) { importController.current = null; setImporting(false); }
    }
  };
  const apply = (ops: Op[]) => { stop(); setNotice(null); void editor.apply(ops); };
  const current = editor.current;
  const active = editor.active && current?.evaluation.clips.get(editor.active);
  const selection = editor.selection;
  const playingOccurrence = current && clock.playing ? occurrenceAt(current.evaluation, clock.position) : null;
  const activeIndex = current ? playingOccurrence?.index ?? (current.evaluation.order[selectedOccurrence] === editor.active
    ? selectedOccurrence : current.evaluation.order.indexOf(editor.active ?? "")) : -1;
  const activeOffset = current ? current.evaluation.order.slice(0, Math.max(0, activeIndex))
    .reduce((sum, id) => sum + duration(current.evaluation.clips.get(id)!.pcm), 0) : 0;
  const seek = (time: number) => {
    if (!current || !editor.active) return;
    const position = activeOffset + time;
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
    if (!current || editor.pending) return;
    try {
      const pcm = current.evaluation.rendered;
      const first = current.wire.clips[0];
      const asset = current.registry.get(sourceKey(first.source));
      const filename = exportFilename({ title: asset?.metadata?.title ?? "Beatopia", bpm: asset?.bpm, key: asset?.metadata?.key });
      const url = downloadUrls.create(new Blob([encodeWav(pcm)], { type: "audio/wav" }));
      const link = document.createElement("a");
      link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
      setNotice(`Downloaded ${filename} · 44100 Hz · 16-bit PCM · ${pcm.channels.length} channels · ${pcm.channels[0].length} frames`);
      const hasLocal = current.wire.clips.some((clip) => clip.source.track_id === "local");
      const windowId = !hasLocal && parsed.entry && track.data ? resolveEntry(parsed.entry, track.data).windowId : undefined;
      if (windowId) {
        try {
          const sessionId = localStorage.getItem("session_id") ?? crypto.randomUUID();
          localStorage.setItem("session_id", sessionId);
          void api.postEvent({ session_id: sessionId, window_id: windowId, action: "export" }).catch(() => setNotice((value) => `${value} · Export telemetry unavailable.`));
        } catch { /* Browser storage availability must not invalidate a download. */ }
      }
    } catch (error) { setNotice(`Export failed: ${(error as Error).message}`); }
  };
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      const target = event.target;
      const typing = target instanceof Element && !!target.closest("input, textarea, select, button, a, [contenteditable]:not([contenteditable='false']), [role='textbox'], [role='slider'], [data-editor-shortcuts='off']");
      const action = editorShortcut(event, typing);
      if (!action || !current || !active || !editor.active || editor.pending || event.defaultPrevented) return;
      event.preventDefault();
      switch (action) {
        case "play": play(); break;
        case "undo": stop(); editor.undo(); break;
        case "redo": stop(); editor.redo(); break;
        case "export": download(); break;
        case "reverse": apply([{ op: "reverse", clip: editor.active }]); break;
        case "up": case "down": apply([{ op: "repitch", clip: editor.active, semitones: action === "up" ? 1 : -1 }]); break;
        case "slice": {
          const at = (transport.current?.position ?? clock.position) - activeOffset;
          if (at > 0 && at < duration(active.pcm)) apply([{ op: "slice", clip: editor.active, at: [at], snap: "none" }]);
          else setNotice("Move the playhead inside the active clip before slicing (S).");
        }
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  });

  const inputs = <>
    <LocalFileDrop disabled={importing || editor.pending || (!!parsed.entry && !current)} onError={setImportError} onFile={(file) => void importSource((signal) => loadLocalFile(file, signal))} />
    {parsed.entry && !current && <a className="block text-sm underline" href="/editor">Open local file editor</a>}
    {importing && <p role="status">Decoding and adding audio…</p>}
    {importError && <p role="alert">{importError}</p>}
  </>;
  if (parsed.error && !current) return <div className="space-y-3">{inputs}<p role={params.get("track") ? "alert" : undefined}>{parsed.error}</p>
    <a className="underline" href="/editor?track=jam_1532881&start=0&end=16&stem=mix">Open jam_1532881 fixture (16 s)</a></div>;
  if (track.isError && !current) return <div>{inputs}<p role="alert">{track.error.message}</p><Button onClick={retry}>Retry track</Button></div>;
  if (parsed.entry && !track.data && !current) return <>{inputs}<p role="status">Loading track metadata…</p></>;
  const metadata = track.data?.track;
  return <div className="space-y-6">
    {inputs}
    <header className="space-y-1">
      <h2 className="text-xl font-medium">{metadata?.title ?? "Local audio editor"}</h2>
      <p>{metadata?.artist ?? "Unknown artist"} · {metadata?.bpm ?? "Unknown"} BPM · {metadata?.key ?? "Unknown key"}</p>
      {parsed.entry && <p className="text-muted-foreground text-sm">{parsed.entry.start}–{parsed.entry.end} s · {parsed.entry.stem} · {acceptance ? "Development metadata snapshot / live public audio" : USE_FIXTURES ? "Fixture library" : "Live library"}</p>}
      {metadata && <p className="text-sm">{metadata.license} · {metadata.attribution}</p>}
    </header>
    {parsed.entry && load.status === "loading" && <p role="status">Loading and decoding audio…</p>}
    {load.error && <div className="space-y-2"><p role="alert">{load.error}</p><Button onClick={retry}>Retry audio</Button>
      {acceptance ? <a className="block text-sm underline" href="/editor/live-editor-checks?track=jam_1047157&start=5&end=15&stem=mix&case=normal">Restore normal live hero audio</a>
        : <p className="text-sm">Fixture fallback: start the web server with NEXT_PUBLIC_USE_FIXTURES=1 and open the fixture link.</p>}</div>}
    {editor.error && <p className="text-destructive" role="alert">{editor.error}</p>}
    {track.data && parsed.entry && current && <StemsDrawer key={`${parsed.entry.trackId}:${parsed.entry.start}:${parsed.entry.end}`}
      detail={track.data} start={parsed.entry.start} end={parsed.entry.end} disabled={importing || editor.pending} error={importError}
      onSelect={(stem) => importSource((signal) => loadStem(stem, track.data!, parsed.entry!.start, parsed.entry!.end, signal))} />}
    {current && <section aria-label="Source licenses" className="space-y-1 text-sm">
      {current.wire.clips.map((clip) => {
        const source = current.registry.get(sourceKey(clip.source));
        return <p key={clip.id}>{clip.id} · {source?.metadata?.title ?? clip.source.track_id} · {clip.source.stem ?? "mix"} · {source?.metadata?.license ?? "License not supplied"} · {source?.metadata?.attribution ?? "Attribution not supplied"}</p>;
      })}
    </section>}
    {current && active && selection && editor.active && <>
      <div className="flex flex-wrap gap-2" aria-label="Choose active clip">
        {current.evaluation.leaves.map((id) => <Button key={id} variant={editor.active === id ? "default" : "outline"} onClick={() => { stop(); editor.select(id); }}>
          {id} · {duration(current.evaluation.clips.get(id)!.pcm).toFixed(3)} s
        </Button>)}
      </div>
      <ArrangementLane evaluation={current.evaluation} selected={activeIndex} disabled={editor.pending}
        onApply={apply} onSelect={(index) => {
          stop(); setSelectedOccurrence(index); editor.select(current.evaluation.order[index]);
          const offset = current.evaluation.order.slice(0, index).reduce((sum, id) => sum + duration(current.evaluation.clips.get(id)!.pcm), 0);
          transport.current?.seek(offset); setClock({ position: offset, playing: false });
        }} />
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
      <p className="text-muted-foreground text-sm">Shortcuts (outside controls): Space play/stop · S split at playhead · R reverse · ↑/↓ repitch ±1 · Ctrl/Cmd+Z undo · Ctrl/Cmd+Shift+Z redo · E export</p>
      <HistoryPanel editor={editor} />
      {editor.pending && <p role="status">Rendering…</p>}
    </>}
    {notice && <p role="status" className="break-words text-sm">{notice}</p>}
  </div>;
}
