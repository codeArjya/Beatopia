// Small async helpers for the waveform decoder (no DOM, unit-tested).

/** Run at most `max` tasks at once; the rest wait in FIFO order. A failing task frees its slot too. */
export function createLimiter(max: number): <T>(task: () => Promise<T>) => Promise<T> {
  let active = 0;
  const queue: (() => void)[] = [];
  const next = () => {
    if (active >= max) return;
    const run = queue.shift();
    if (run) run();
  };
  return <T>(task: () => Promise<T>) =>
    new Promise<T>((resolve, reject) => {
      queue.push(() => {
        active++;
        task()
          .then(resolve, reject)
          .finally(() => {
            active--;
            next();
          });
      });
      next();
    });
}

/** Least-recently-used map with a fixed size. `get` refreshes an entry; `set` evicts the oldest beyond `size`. */
export class LruCache<K, V> {
  private readonly map = new Map<K, V>();
  constructor(private readonly size: number) {}

  get(key: K): V | undefined {
    const v = this.map.get(key);
    if (v === undefined) return undefined;
    this.map.delete(key);
    this.map.set(key, v);
    return v;
  }

  set(key: K, value: V): void {
    this.map.delete(key);
    this.map.set(key, value);
    while (this.map.size > this.size) {
      const oldest = this.map.keys().next().value as K;
      this.map.delete(oldest);
    }
  }

  delete(key: K, only?: V): void {
    if (only === undefined || this.map.get(key) === only) this.map.delete(key);
  }

  keys(): K[] {
    return [...this.map.keys()];
  }
}
