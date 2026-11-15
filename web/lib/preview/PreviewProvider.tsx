"use client";

import { createContext, useContext, useEffect, useLayoutEffect, useState, useSyncExternalStore, type ReactNode } from "react";

import type { PreviewItem } from "./loop";
import { IDLE_SNAPSHOT, PreviewPlayer, type PreviewSnapshot, type PreviewStatus } from "./player";

const PreviewContext = createContext<PreviewPlayer | null>(null);

/** Owns the one shared preview player. Mounted once in app/providers.tsx. */
export function PreviewProvider({ children }: { children: ReactNode }) {
  // Lazily created; the constructor touches no DOM, the <audio> element is made on first use (client only).
  const [player] = useState(() => new PreviewPlayer());
  useEffect(() => () => player.dispose(), [player]);
  return <PreviewContext.Provider value={player}>{children}</PreviewContext.Provider>;
}

/** The shared player (play / stop / toggle / warm / progress). Calling its methods never re-renders by itself. */
export function usePreviewPlayer(): PreviewPlayer {
  const player = useContext(PreviewContext);
  if (!player) throw new Error("usePreviewPlayer must be used inside <PreviewProvider>");
  return player;
}

const serverSnapshot = (): PreviewSnapshot => IDLE_SNAPSHOT;

/** The whole preview state (which item, which status). Re-renders on every change. */
export function usePreviewSnapshot(): PreviewSnapshot {
  const player = usePreviewPlayer();
  return useSyncExternalStore(player.subscribe, player.getSnapshot, serverSnapshot);
}

/** Status of one caller's preview: "idle" unless `id` is the active item. */
export function usePreviewStatus(id: string): PreviewStatus {
  const player = usePreviewPlayer();
  // Selecting a primitive: cards whose status didn't change skip re-rendering.
  return useSyncExternalStore(
    player.subscribe,
    () => {
      const s = player.getSnapshot();
      return s.item?.id === id ? s.status : "idle";
    },
    () => "idle",
  );
}

/**
 * Stop the preview when the calling page is hidden or unmounted. With cacheComponents, Next hides left routes
 * with <Activity> instead of unmounting them; a useLayoutEffect cleanup runs synchronously on hide.
 */
export function useStopPreviewOnHide(): void {
  const player = usePreviewPlayer();
  useLayoutEffect(() => () => player.stop(), [player]);
}

export type { PreviewItem, PreviewSnapshot, PreviewStatus };
