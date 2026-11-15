import { afterEach, expect, it, vi } from "vitest";
import { renderOffline } from "./native-offline";
import { SAMPLE_RATE } from "./types";

const pcm = { sampleRate: SAMPLE_RATE, channels: [new Float32Array(8)] };
vi.mock("./decode", () => ({
  toAudioBuffer: () => ({}),
  fromAudioBuffer: () => ({ sampleRate: 44100, channels: [new Float32Array(8)] }),
}));
afterEach(() => vi.unstubAllGlobals());

it("releases native offline source/filter references after success and rendering failure", async () => {
  for (const failed of [false, true]) {
    const filter = { type: "lowpass", frequency: { setValueAtTime: vi.fn() }, Q: { setValueAtTime: vi.fn() },
      connect: vi.fn(), disconnect: vi.fn() };
    const node = { buffer: null, playbackRate: { setValueAtTime: vi.fn() },
      connect: vi.fn(() => filter), disconnect: vi.fn(), start: vi.fn(), stop: vi.fn() };
    const constructor = vi.fn(function () { return {
      createBufferSource: () => node, createBiquadFilter: () => filter, destination: {},
      startRendering: async () => { if (failed) throw new Error("render failed"); return {}; },
    }; });
    vi.stubGlobal("OfflineAudioContext", constructor);
    const render = renderOffline(pcm, { op: "filter", clip: "c1", type: "lowpass", freq_hz: 1000 }, null);
    if (failed) await expect(render).rejects.toThrow("render failed");
    else expect(await render).toEqual(pcm);
    expect(constructor).toHaveBeenCalledWith(1, 8, 44100);
    expect(node.stop).toHaveBeenCalledWith(8 / SAMPLE_RATE);
    expect(node.disconnect).toHaveBeenCalledOnce(); expect(filter.disconnect).toHaveBeenCalledOnce();
    expect(node.buffer).toBeNull();
  }
});
