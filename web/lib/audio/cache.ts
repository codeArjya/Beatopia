import type { EvaluatedClip } from "./evaluate";

export interface ReplayPrefix {
  clips: ReadonlyMap<string, EvaluatedClip>;
  leaves: readonly string[];
  order: readonly string[];
  sliced: ReadonlySet<string>;
  minimumChannels: 1 | 2;
}

/** Store-scoped LRU. PCM is immutable; shared backing buffers count only once. */
export class PrefixCache {
  private entries = new Map<string, ReplayPrefix>();
  private identities = new WeakMap<object, number>();
  private nextIdentity = 0;
  private generation = 0;
  constructor(readonly maxBytes = 64 * 1024 * 1024, readonly maxEntries = 12) {
    if (!Number.isSafeInteger(maxBytes) || maxBytes < 0 || !Number.isSafeInteger(maxEntries) || maxEntries < 0) {
      throw new Error("Cache limits must be nonnegative integers.");
    }
  }
  identity(value: object): number {
    let id = this.identities.get(value);
    if (id === undefined) { id = ++this.nextIdentity; this.identities.set(value, id); }
    return id;
  }
  get epoch() { return this.generation; }
  get stats() {
    const buffers = new Set<ArrayBufferLike>();
    let bytes = 0;
    for (const [key, prefix] of this.entries) {
      bytes += key.length * 2 + (prefix.leaves.length + prefix.order.length + prefix.sliced.size) * 64;
      for (const clip of prefix.clips.values()) {
        bytes += 128 + clip.beatTimes.length * 8;
        for (const channel of clip.pcm.channels) buffers.add(channel.buffer);
      }
    }
    for (const buffer of buffers) bytes += buffer.byteLength;
    return { entries: this.entries.size, bytes };
  }
  get(key: string): ReplayPrefix | undefined {
    const value = this.entries.get(key);
    if (value) { this.entries.delete(key); this.entries.set(key, value); }
    return value;
  }
  set(key: string, value: ReplayPrefix, epoch: number): void {
    if (epoch !== this.generation) return;
    this.entries.delete(key);
    this.entries.set(key, value);
    while (this.entries.size && (this.entries.size > this.maxEntries || this.stats.bytes > this.maxBytes)) {
      this.entries.delete(this.entries.keys().next().value!);
    }
  }
  clear(): void { this.entries.clear(); this.generation++; }
}
