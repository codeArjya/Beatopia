"use client";

import { cn } from "cn";
import { useEffect, useRef, useState } from "react";

import { usePreviewPlayer, usePreviewStatus, type PreviewItem } from "@/lib/preview/PreviewProvider";
import { normalizePeaks } from "@/lib/waveform/peaks";
import { usePeaks } from "@/lib/waveform/usePeaks";

/**
 * Static waveform of a result's window on a plain canvas (no wavesurfer per card), with a playhead overlay while
 * the window is the active preview. Decoding starts once the card nears the viewport. Decorative: the play button
 * and the card carry the accessible controls. A failed decode (CORS, bad file) leaves a flat line.
 */
export function MiniWaveform({ item, className }: { item: PreviewItem; className?: string }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const baseRef = useRef<HTMLCanvasElement>(null);
  const playedRef = useRef<HTMLCanvasElement>(null);
  const clipRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HTMLDivElement>(null);

  const [inView, setInView] = useState(false);
  const [width, setWidth] = useState(0);
  const peaks = usePeaks(item.url, item.start, item.end, inView);
  const status = usePreviewStatus(item.id);
  const player = usePreviewPlayer();
  const active = status === "playing" || status === "loading";

  // Start decoding once the card is within 200 px of the viewport; never stop after that.
  useEffect(() => {
    const el = boxRef.current;
    if (!el || inView) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setInView(true);
      },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [inView]);

  // CSS width drives the canvas size (cards reflow between 1 and 2 columns).
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const data = peaks.data;
  useEffect(() => {
    if (!width) return;
    const norm = data ? normalizePeaks(data) : null;
    for (const canvas of [baseRef.current, playedRef.current]) {
      if (canvas) draw(canvas, norm, width);
    }
  }, [data, width]);

  // Playhead: poll the shared player on rAF only while this window is the active preview.
  useEffect(() => {
    const clip = clipRef.current;
    const head = headRef.current;
    if (!clip || !head) return;
    head.hidden = !active;
    if (!active) {
      clip.style.clipPath = "inset(0 100% 0 0)";
      return;
    }
    let raf = 0;
    const tick = () => {
      const p = player.progress(item.id);
      clip.style.clipPath = `inset(0 ${(1 - p) * 100}% 0 0)`;
      head.style.left = `${p * 100}%`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, player, item.id]);

  return (
    <div
      ref={boxRef}
      aria-hidden
      className={cn("relative h-12 overflow-hidden rounded-md bg-muted/30", peaks.isFetching && !data && "animate-pulse", className)}
    >
      <canvas ref={baseRef} className="absolute inset-0 size-full text-muted-foreground opacity-60" />
      <div ref={clipRef} className="absolute inset-0" style={{ clipPath: "inset(0 100% 0 0)" }}>
        <canvas ref={playedRef} className="absolute inset-0 size-full text-primary" />
      </div>
      <div ref={headRef} hidden className="absolute inset-y-0 left-0 -ml-px w-0.5 bg-primary" />
    </div>
  );
}

const BAR_GAP_RATIO = 0.35;

/** Mirrored bars at the device pixel ratio, in the canvas's CSS `color`. `peaks: null` = a flat center line. */
function draw(canvas: HTMLCanvasElement, peaks: number[] | null, cssWidth: number) {
  const dpr = window.devicePixelRatio || 1;
  const cssHeight = canvas.clientHeight || 48;
  const w = Math.round(cssWidth * dpr);
  const h = Math.round(cssHeight * dpr);
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
  const g = canvas.getContext("2d");
  if (!g) return;
  g.clearRect(0, 0, w, h);
  g.fillStyle = getComputedStyle(canvas).color;

  const mid = h / 2;
  if (!peaks || peaks.length === 0) {
    g.fillRect(0, Math.round(mid - dpr / 2), w, Math.max(1, Math.round(dpr)));
    return;
  }
  const step = w / peaks.length;
  const barW = Math.max(dpr, step * (1 - BAR_GAP_RATIO));
  const maxHalf = mid - dpr; // keep a pixel of headroom
  for (let i = 0; i < peaks.length; i++) {
    const half = Math.max(dpr / 2, peaks[i] * maxHalf);
    g.fillRect(i * step + (step - barW) / 2, mid - half, barW, half * 2);
  }
}
