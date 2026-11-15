import { fromAudioBuffer, toAudioBuffer } from "./decode";
import type { OfflineRenderer } from "./evaluate";
import { planOfflineFrames } from "./offline";
import { renderGranular } from "./tone-offline";
import { SAMPLE_RATE } from "./types";

/** Browser-only adapter; importing it does not construct a real-time audio context. */
export const renderOffline: OfflineRenderer = async (pcm, op, bpm) => {
  const plan = planOfflineFrames(pcm, op, bpm);
  if (plan.granular) return renderGranular(pcm, plan);
  const context = new OfflineAudioContext(pcm.channels.length, plan.frames, SAMPLE_RATE);
  const source = context.createBufferSource();
  let filter: BiquadFilterNode | undefined;
  try {
    source.buffer = toAudioBuffer(context, pcm);
    source.playbackRate.setValueAtTime(plan.rate, 0);
    if (op.op === "filter") {
      filter = context.createBiquadFilter();
      filter.type = op.type;
      filter.frequency.setValueAtTime(op.freq_hz, 0);
      filter.Q.setValueAtTime(Math.SQRT1_2, 0);
      source.connect(filter).connect(context.destination);
    } else source.connect(context.destination);
    source.start(0);
    source.stop(plan.frames / SAMPLE_RATE);
    return fromAudioBuffer(await context.startRendering());
  } finally {
    source.disconnect();
    source.buffer = null;
    filter?.disconnect();
  }
};
