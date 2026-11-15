/** Download URLs live briefly, and are also released when their editor unmounts. */
export class ObjectUrls {
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  create(blob: Blob): string {
    const url = URL.createObjectURL(blob);
    this.timers.set(url, setTimeout(() => this.release(url), 1000));
    return url;
  }
  private release(url: string): void {
    const timer = this.timers.get(url);
    if (timer !== undefined) clearTimeout(timer);
    this.timers.delete(url);
    URL.revokeObjectURL(url);
  }
  dispose(): void { for (const url of this.timers.keys()) this.release(url); }
}
