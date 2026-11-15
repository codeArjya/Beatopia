// The app's one preview player: a single HTMLAudioElement, so only one preview plays at a time.
// Framework-free external store (subscribe/getSnapshot) for useSyncExternalStore. Browser-only: create it on the client.

import { loopSeekTarget, windowProgress, type PreviewItem } from "./loop";

export type PreviewStatus = "idle" | "loading" | "playing" | "error";

/** Immutable; replaced (never mutated) on every change so useSyncExternalStore can compare by reference. */
export type PreviewSnapshot = {
  readonly item: PreviewItem | null;
  readonly status: PreviewStatus;
};

export const IDLE_SNAPSHOT: PreviewSnapshot = Object.freeze({ item: null, status: "idle" });

export class PreviewPlayer {
  private audio: HTMLAudioElement | null = null;
  private snapshot: PreviewSnapshot = IDLE_SNAPSHOT;
  private readonly listeners = new Set<() => void>();
  private raf = 0;
  /** Bumped on every play/stop, so a late play() rejection from a superseded preview is ignored. */
  private epoch = 0;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): PreviewSnapshot => this.snapshot;

  /** Start `item` from its window start. Call from a user gesture (autoplay policy) for the first play. */
  play(item: PreviewItem): void {
    const audio = this.element();
    const epoch = ++this.epoch;
    if (!sameSrc(audio, item.url)) {
      audio.src = item.url;
    }
    // Before metadata loads this sets the "default playback start position", applied once it loads.
    audio.currentTime = item.start;
    this.set({ item, status: "loading" });
    audio.play().then(
      // Switching windows on an element that is already playing fires no new "playing" event.
      () => {
        if (epoch === this.epoch) this.setStatus("playing");
      },
      (e: unknown) => {
        if (epoch !== this.epoch) return; // superseded by another play/stop (AbortError)
        console.warn("[preview] play failed", e);
        this.set({ item, status: "error" });
        this.stopLoop();
      },
    );
    this.startLoop();
  }

  stop(): void {
    this.epoch++;
    this.stopLoop();
    this.audio?.pause();
    if (this.snapshot !== IDLE_SNAPSHOT) this.set(IDLE_SNAPSHOT);
  }

  /** Stop if `item` is the active preview (loading or playing), else play it. */
  toggle(item: PreviewItem): void {
    const { item: active, status } = this.snapshot;
    if (active?.id === item.id && (status === "playing" || status === "loading")) this.stop();
    else this.play(item);
  }

  /** Hover/focus warm-up: start buffering `url`, but only while nothing is active (never interrupts a preview). */
  warm(url: string): void {
    if (this.snapshot.item) return;
    const audio = this.element();
    if (sameSrc(audio, url)) return;
    audio.src = url;
    audio.load();
  }

  /** Playhead of the active preview as a fraction of its window, or 0. Cheap; poll it from a rAF loop. */
  progress(id: string): number {
    const { item } = this.snapshot;
    if (!item || item.id !== id || !this.audio) return 0;
    return windowProgress(this.audio.currentTime, item.start, item.end);
  }

  dispose(): void {
    this.stop();
    if (this.audio) {
      this.audio.removeAttribute("src");
      this.audio.load();
    }
    // Listeners are left alone: under StrictMode the provider's effect re-runs while subscribers stay mounted.
  }

  private element(): HTMLAudioElement {
    if (this.audio) return this.audio;
    const audio = new Audio();
    audio.preload = "auto";
    // Media events only move status; the rAF loop owns the window boundary.
    audio.addEventListener("playing", () => this.setStatus("playing"));
    audio.addEventListener("waiting", () => this.setStatus("loading"));
    audio.addEventListener("error", () => {
      if (!this.snapshot.item) return; // a failed warm-up is not the user's problem
      console.warn("[preview] media error", audio.error?.code, audio.error?.message);
      this.stopLoop();
      this.setStatus("error");
    });
    // Background tabs get no rAF; timeupdate (~4 Hz) still keeps the loop inside the window there, a bit late.
    audio.addEventListener("timeupdate", () => this.checkBoundary());
    // A window that ends at the file end: the element stops on its own before the rAF check can wrap it.
    audio.addEventListener("ended", () => {
      const { item } = this.snapshot;
      if (!item) return;
      audio.currentTime = item.start;
      void audio.play().catch(() => undefined);
    });
    this.audio = audio;
    return audio;
  }

  private startLoop(): void {
    if (this.raf) return;
    const tick = () => {
      const { item } = this.snapshot;
      if (!item || !this.audio) {
        this.raf = 0;
        return;
      }
      this.checkBoundary();
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  private checkBoundary(): void {
    const { item } = this.snapshot;
    const audio = this.audio;
    // Only correct the position once media data is there; before that, currentTime is the pending start.
    if (!item || !audio || audio.readyState < HTMLMediaElement.HAVE_METADATA || audio.seeking) return;
    const target = loopSeekTarget(audio.currentTime, item.start, item.end);
    if (target !== null) audio.currentTime = target;
  }

  private stopLoop(): void {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  private setStatus(status: PreviewStatus): void {
    const { item } = this.snapshot;
    if (!item || this.snapshot.status === status) return;
    this.set({ item, status });
  }

  private set(next: PreviewSnapshot): void {
    this.snapshot = next;
    for (const l of this.listeners) l();
  }
}

/** `audio.src` is always absolute; item urls may be relative (`/fixtures/audio/mix.wav`). */
function sameSrc(audio: HTMLAudioElement, url: string): boolean {
  if (!audio.src) return false;
  try {
    return audio.src === new URL(url, window.location.href).href;
  } catch {
    return false;
  }
}
