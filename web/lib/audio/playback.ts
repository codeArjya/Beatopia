import { toAudioBuffer } from "./decode";
import { duration } from "./pcm";
import { SAMPLE_RATE, type PcmBuffer } from "./types";
import type { Evaluation } from "./evaluate";

export function occurrenceAt(evaluation: Evaluation, position: number): { id: string; offset: number; index: number } | null {
  let offset = 0;
  for (const [index, id] of evaluation.order.entries()) {
    const length = duration(evaluation.clips.get(id)!.pcm);
    if (position < offset + length) return { id, offset, index };
    offset += length;
  }
  return null;
}

export function playbackPosition(elapsed: number, offset: number, length: number, loop: boolean): number {
  if (length <= 0) return 0;
  const position = Math.max(0, elapsed + offset);
  return loop ? position % length : Math.min(position, length);
}
export class PlaybackController {
  private context: AudioContext | null = null;
  private node: AudioBufferSourceNode | null = null;
  private started = 0;
  private offset = 0;
  private length = 0;
  private looping = false;
  private generation = 0;
  get playing(): boolean { return this.node !== null; }
  get position(): number {
    return this.node && this.context
      ? playbackPosition(this.context.currentTime - this.started, this.offset, this.length, this.looping) : this.offset;
  }
  async play(pcm: PcmBuffer, offset = 0, loop = false): Promise<void> {
    this.stop();
    const generation = this.generation;
    // Called only by an explicit play/seek gesture.
    this.context ??= new AudioContext({ sampleRate: SAMPLE_RATE });
    await this.context.resume();
    if (generation !== this.generation) return;
    this.length = duration(pcm);
    this.offset = offset >= this.length ? 0 : Math.max(0, offset);
    this.looping = loop;
    const node = this.context.createBufferSource();
    node.buffer = toAudioBuffer(this.context, pcm);
    node.loop = loop;
    node.connect(this.context.destination);
    node.onended = () => {
      if (this.node === node) { this.offset = this.length; this.node = null; }
      node.disconnect();
    };
    this.node = node;
    this.started = this.context.currentTime;
    node.start(0, this.offset);
  }
  stop(): void {
    this.generation++;
    this.offset = this.position;
    if (this.node) {
      this.node.onended = null;
      this.node.stop();
      this.node.disconnect();
      this.node = null;
    }
  }
  seek(position: number): void { this.stop(); this.offset = Math.max(0, position); }
  setLoop(loop: boolean): void {
    this.offset = this.position;
    if (this.context) this.started = this.context.currentTime;
    this.looping = loop;
    if (this.node) this.node.loop = loop;
  }
  dispose(): void { this.stop(); void this.context?.close(); this.context = null; }
}
