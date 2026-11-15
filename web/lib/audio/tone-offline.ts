import { fromAudioBuffer } from "./decode";
import { allocationBytes, requireRange, validatePcm } from "./pcm";
import { createSerialQueue } from "./serial";
import { AudioEngineError, SAMPLE_RATE, type PcmBuffer } from "./types";

// Tone.Offline temporarily switches its global context. All editor Tone work uses this queue.
const enqueue = createSerialQueue();
export function renderGranular(pcm: PcmBuffer, plan: { rate: number; semitones: number; frames: number }): Promise<PcmBuffer> {
  validatePcm(pcm);
  allocationBytes(plan.frames, pcm.channels.length);
  requireRange(plan.rate, 0.001, 1000, "Grain playback rate");
  requireRange(plan.semitones, -24, 24, "Semitones");
  if (plan.frames < 1 || !pcm.channels[0].length) throw new AudioEngineError("bad_request", "Granular rendering requires nonempty audio.");
  return enqueue(async () => {
    const Tone = await import("tone");
    const original = Tone.getContext();
    let context: InstanceType<typeof Tone.OfflineContext> | undefined;
    let player: InstanceType<typeof Tone.GrainPlayer> | undefined;
    let rendered: Awaited<ReturnType<typeof Tone.Offline>> | undefined;
    try {
      rendered = await Tone.Offline((offline) => {
        context = offline;
        const buffer = offline.createBuffer(pcm.channels.length, pcm.channels[0].length, SAMPLE_RATE);
        pcm.channels.forEach((channel, index) => buffer.copyToChannel(new Float32Array(channel), index));
        // Short clips use smaller grains; no loop or implicit source crossfade is added.
        const grainSize = Math.min(0.2, buffer.duration / 4);
        player = new Tone.GrainPlayer({ context: offline, url: buffer,
          playbackRate: plan.rate, detune: plan.semitones * 100,
          grainSize, overlap: grainSize / 2, loop: false });
        player.toDestination().start(0, 0).stop(plan.frames / SAMPLE_RATE);
      // Tone multiplies seconds by sampleRate, then Web Audio truncates to frames.
      // Half a sample guards against e.g. 15 / 44100 * 44100 becoming 14.999999999999998.
      // The allocated buffer still has exactly plan.frames; stop remains at its exact end.
      }, (plan.frames + 0.5) / SAMPLE_RATE, pcm.channels.length, SAMPLE_RATE);
      const buffer = rendered.get();
      if (!buffer || buffer.length !== plan.frames) throw new Error("Tone returned an unexpected frame count.");
      return fromAudioBuffer(buffer);
    } finally {
      // Installed Tone.Offline lacks a finally around its callback. Restore even on failure.
      Tone.setContext(original);
      player?.dispose();
      rendered?.dispose();
      context?.dispose();
    }
  });
}
