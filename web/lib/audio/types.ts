/** Engine-owned channel arrays; operations never mutate their inputs. */
export interface PcmBuffer {
  readonly sampleRate: number;
  readonly channels: readonly Float32Array[];
}

export const SAMPLE_RATE = 44_100;
export const MAX_DURATION_S = 60;

export class AudioEngineError extends Error {
  constructor(
    readonly code: "bad_request" | "range_too_long" | "clip_is_sliced",
    message: string,
  ) {
    super(message);
    this.name = "AudioEngineError";
  }
}
