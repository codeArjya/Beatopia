import { describe, expect, it, vi } from "vitest";
import fixture from "../../shared/fixtures/assist.json";
import type { AssistRequest, AssistResponse, Op } from "../lib/types/api";
import { assistRequest, assistResponse } from "../lib/audio/assist";
import { sourceKey } from "../lib/audio/evaluate";
import { SAMPLE_RATE } from "../lib/audio/types";
import { createEditorStore } from "./editor";
import { createAssistStore } from "./assist";

async function setup() {
  const editor = createEditorStore();
  const source = { track_id: "t", stem: "mix" as const, audio_url: "https://audio.test/mix.wav", start_s: 5, end_s: 5 + 8 / SAMPLE_RATE };
  await editor.getState().initialize({ bpm: 90, clips: [{ id: "c1", source }], ops: [], arrangement: [] },
    new Map([[sourceKey(source), { origin: 5, beatTimes: [2, 4, 6].map((frame) => 5 + frame / SAMPLE_RATE), bpm: 90,
      pcm: { sampleRate: SAMPLE_RATE, channels: [Float32Array.from([1, 2, 3, 4, 5, 6, 7, 8])] },
      metadata: { title: "Test", license: "CC0", attribution: "Test artist" } }]]));
  return editor;
}
const response = (ops: Op[]): AssistResponse => ({ reply: "Review these edits.", ops });

describe("assist transactions", () => {
  it("sends exact generated wire fields and previews the actual fixture slice/reverse without mutations", async () => {
    const editor = await setup();
    const request = vi.fn<(body: AssistRequest) => Promise<AssistResponse>>(async () => assistResponse(fixture));
    const chat = createAssistStore(editor, request);
    const before = editor.getState().current;
    await chat.getState().send("chop into 4");
    const body = request.mock.calls[0][0];
    expect(body).toEqual({ messages: [{ role: "user", content: "chop into 4" }], editor: before!.wire });
    expect(Object.keys(body)).toEqual(["messages", "editor"]);
    expect(Object.keys(body.editor).sort()).toEqual(["arrangement", "bpm", "clips", "ops"]);
    expect(Object.keys(body.editor.clips[0]).sort()).toEqual(["id", "source"]);
    expect(Object.keys(body.editor.clips[0].source).sort()).toEqual(["audio_url", "end_s", "start_s", "stem", "track_id"]);
    expect(JSON.stringify(body)).not.toMatch(/pcm|registry|selection|revision|metadata|license|past/);
    expect(chat.getState().proposal!.evaluation.leaves).toContain("c1.4");
    expect(Array.from(chat.getState().proposal!.evaluation.rendered.channels[0])).toEqual([1, 2, 3, 4, 5, 6, 8, 7]);
    expect(editor.getState().current).toBe(before);
    expect(editor.getState().past).toEqual([]);
    chat.getState().discard();
    expect(chat.getState().proposal).toBeNull();
    expect(editor.getState().current).toBe(before);
  });

  it("applies sequential fixture ops as one undo step; c1.4 stays usable and redo is exact", async () => {
    const editor = await setup(); const before = editor.getState().current;
    const chat = createAssistStore(editor, async () => assistResponse(fixture));
    await chat.getState().send("chop and reverse");
    expect(await chat.getState().apply()).toBe(true);
    const after = editor.getState().current;
    expect(after!.wire.clips).toHaveLength(1);
    expect(after!.wire.ops).toEqual(fixture.ops);
    expect(editor.getState().past).toHaveLength(1);
    editor.getState().undo(); expect(editor.getState().current).toBe(before);
    editor.getState().redo(); expect(editor.getState().current).toBe(after);
    expect(await editor.getState().apply([{ op: "reverse", clip: "c1.4" }])).toBe(true);
  });

  it.each([
    [{ op: "reverse", clip: "c1" }, { op: "reverse", clip: "absent" }],
    [{ op: "slice", clip: "c1", count: 4, snap: "none" }, { op: "reverse", clip: "c1" }],
    [{ op: "slice", clip: "c1", at: [6 / SAMPLE_RATE, 2 / SAMPLE_RATE], snap: "none" }],
    [{ op: "reverse", clip: "c1" }, { op: "repitch", clip: "c1", semitones: 25 }],
    [{ op: "reverse", clip: "c1" }, { op: "loop", clip: "c1", times: 1.5 }],
    [{ op: "erase", clip: "c1" }],
    [{ op: "slice", clip: "c1", count: 4, snap: "invalid" }],
    [{ op: "stretch_to_bpm", clip: "c1", target_bpm: 120, keep_pitch: "false" }],
  ])("rejects a malformed or semantically invalid whole batch %j", async (...ops) => {
    const editor = await setup(); const before = editor.getState().current;
    const chat = createAssistStore(editor, async () => ({ reply: "Bad batch", ops }) as AssistResponse);
    await chat.getState().send("edit");
    expect(chat.getState().error).toBeTruthy();
    expect(chat.getState().proposal).toBeNull();
    expect(await chat.getState().apply()).toBe(false);
    expect(editor.getState().current).toBe(before);
    expect(editor.getState().past).toEqual([]);
    expect(editor.getState().future).toEqual([]);
  });

  it("rejects changes during request and between preview/apply, even an edit followed by undo", async () => {
    const editor = await setup();
    let resolve!: (result: AssistResponse) => void;
    const chat = createAssistStore(editor, () => new Promise((done) => { resolve = done; }));
    const pending = chat.getState().send("reverse");
    await editor.getState().apply([{ op: "reverse", clip: "c1" }]);
    const edited = editor.getState().current;
    resolve(response([{ op: "reverse", clip: "c1" }])); await pending;
    expect(chat.getState().error).toContain("editor changed");
    expect(editor.getState().current).toBe(edited);
    const retry = chat.getState().retry();
    resolve(response([{ op: "reverse", clip: "c1" }])); await retry;
    editor.getState().undo(); editor.getState().redo();
    expect(await chat.getState().apply()).toBe(false);
    expect(editor.getState().current).toBe(edited);
    expect(editor.getState().past).toHaveLength(1);
  });

  it("retries explicitly with intact conversation and latest edits, without duplicating the user message", async () => {
    const editor = await setup();
    const request = vi.fn<(body: AssistRequest) => Promise<AssistResponse>>()
      .mockRejectedValueOnce(new Error("Assist unavailable (503)"))
      .mockResolvedValue(response([{ op: "reverse", clip: "c1" }]));
    const chat = createAssistStore(editor, request);
    await chat.getState().send("reverse");
    expect(request).toHaveBeenCalledTimes(1);
    expect(await editor.getState().apply([{ op: "gain", clip: "c1", db: -3 }])).toBe(true);
    const edited = editor.getState().current;
    await chat.getState().retry();
    expect(request.mock.calls[1][0].messages).toEqual([{ role: "user", content: "reverse" }]);
    expect(request.mock.calls[1][0].editor).toEqual(edited!.wire);
    expect(editor.getState().current).toBe(edited);
    await chat.getState().apply();
    await chat.getState().send("again");
    expect(request.mock.calls[2][0].messages).toEqual([
      { role: "user", content: "reverse" }, { role: "assistant", content: "Review these edits." }, { role: "user", content: "again" },
    ]);
  });

  it("blocks mixed local requests while preserving manual editing; cleared sessions ignore late results", async () => {
    const editor = await setup();
    const request = vi.fn(async () => response([]));
    const local = { track_id: "local", audio_url: "blob:test", start_s: 0, end_s: 1 / SAMPLE_RATE };
    await editor.getState().addSource(local, { pcm: { sampleRate: SAMPLE_RATE, channels: [new Float32Array([0.5])] }, origin: 0, beatTimes: [], bpm: null });
    const chat = createAssistStore(editor, request);
    await chat.getState().send("edit");
    expect(request).not.toHaveBeenCalled();
    expect(chat.getState().error).toContain("local audio");
    expect(await editor.getState().apply([{ op: "reverse", clip: "c2" }])).toBe(true);
    let release!: (value: AssistResponse) => void;
    const editor2 = await setup();
    const late = createAssistStore(editor2, () => new Promise((done) => { release = done; }));
    const pending = late.getState().send("reverse");
    late.getState().clear(); release(response([{ op: "reverse", clip: "c1" }])); await pending;
    expect(late.getState().messages).toEqual([]);
    expect(late.getState().proposal).toBeNull();
    expect(editor2.getState().past).toEqual([]);
  });

  it("rejects runtime extras and nonfinite values against the generated schema", async () => {
    const editor = await setup();
    expect(() => assistRequest([], { ...editor.getState().toEditorState()!, selection: [0, 1] } as never)).toThrow("AssistRequest");
    expect(() => assistResponse({ reply: "bad", ops: [{ op: "gain", clip: "c1", db: NaN }] })).toThrow("invalid");
    expect(() => assistResponse({ reply: "bad", ops: [{ op: "reverse", clip: "c1", pcm: [] }] })).toThrow("invalid");
  });

  it("rejects excessive output before Apply and preserves redo and all current audio", async () => {
    const editor = createEditorStore();
    const source = { track_id: "t", audio_url: "t.wav", start_s: 0, end_s: 5 };
    await editor.getState().initialize({ clips: [{ id: "c1", source }], ops: [] },
      new Map([[sourceKey(source), { origin: 0, beatTimes: [], bpm: null,
        pcm: { sampleRate: SAMPLE_RATE, channels: [new Float32Array(5 * SAMPLE_RATE)] } }]]));
    await editor.getState().apply([{ op: "reverse", clip: "c1" }]); editor.getState().undo();
    const before = editor.getState().current, future = editor.getState().future;
    const chat = createAssistStore(editor, async () => response([
      { op: "reverse", clip: "c1" }, { op: "loop", clip: "c1", times: 16 },
    ]));
    await chat.getState().send("loop");
    expect(chat.getState().error).toContain("60 seconds");
    expect(chat.getState().proposal).toBeNull();
    expect(editor.getState().current).toBe(before);
    expect(editor.getState().future).toBe(future);
    expect(editor.getState().past).toEqual([]);
  });
});
