import { describe, expect, it } from "vitest";

import {
  checkImportHead,
  checkImportMeta,
  fileExtension,
  MAX_IMPORT_BYTES,
  sniffAudio,
  validateImportFile,
} from "./validate";

const bytes = (...parts: (string | number[])[]) =>
  new Uint8Array(parts.flatMap((p) => (typeof p === "string" ? [...p].map((c) => c.charCodeAt(0)) : p)));

const WAV = bytes("RIFF", [0, 0, 0, 0], "WAVE", "fmt ");
const MP3_ID3 = bytes("ID3", [4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
const MP3_SYNC = bytes([0xff, 0xfb, 0x90, 0x64]);
const FLAC = bytes("fLaC", [0, 0, 0, 34]);
const OGG = bytes("OggS", [0, 2]);
const M4A = bytes([0, 0, 0, 32], "ftypM4A ");

describe("fileExtension", () => {
  it("lowercases the last extension and handles odd names", () => {
    expect(fileExtension("Loop.WAV")).toBe("wav");
    expect(fileExtension("my.loop.final.mp3")).toBe("mp3");
    expect(fileExtension("noext")).toBe("");
    expect(fileExtension(".wav")).toBe(""); // a dotfile, not a .wav
    expect(fileExtension("trailing.")).toBe("");
  });
});

describe("checkImportMeta", () => {
  const ok = { name: "loop.wav", size: 1_000_000, type: "audio/wav" };

  it("accepts each supported extension, any case", () => {
    for (const name of ["a.wav", "a.mp3", "a.flac", "a.m4a", "a.ogg", "A.MP3"]) {
      expect(checkImportMeta({ ...ok, name })).toMatchObject({ ok: true });
    }
  });

  it("rejects a .txt and a file with no extension, naming the formats", () => {
    const txt = checkImportMeta({ name: "notes.txt", size: 10, type: "text/plain" });
    expect(txt).toMatchObject({ ok: false, code: "unsupported_format" });
    expect(!txt.ok && txt.message).toMatch(/\.txt.*WAV, MP3, FLAC, M4A or OGG/);
    expect(checkImportMeta({ name: "noext", size: 10, type: "" })).toMatchObject({ ok: false, code: "unsupported_format" });
  });

  it("is lenient about MIME (unknown, octet-stream, video/* containers) but rejects clearly non-audio", () => {
    for (const type of ["", "audio/mpeg", "audio/x-m4a", "application/octet-stream", "video/ogg", "video/mp4", "application/ogg"]) {
      expect(checkImportMeta({ ...ok, type })).toMatchObject({ ok: true });
    }
    expect(checkImportMeta({ ...ok, name: "x.mp3", type: "text/plain" })).toMatchObject({ ok: false, code: "unsupported_format" });
    expect(checkImportMeta({ ...ok, name: "x.wav", type: "image/png" })).toMatchObject({ ok: false });
  });

  it("enforces the 25 MiB limit exactly, and rejects empty files", () => {
    expect(checkImportMeta({ ...ok, size: MAX_IMPORT_BYTES })).toMatchObject({ ok: true });
    const over = checkImportMeta({ ...ok, size: MAX_IMPORT_BYTES + 1 });
    expect(over).toMatchObject({ ok: false, code: "upload_too_large" });
    const big = checkImportMeta({ ...ok, size: 30 * 1024 * 1024 });
    expect(!big.ok && big.message).toMatch(/30 MB.*25 MB/);
    expect(checkImportMeta({ ...ok, size: 0 })).toMatchObject({ ok: false, code: "empty_file" });
  });
});

describe("sniffAudio / checkImportHead", () => {
  it("recognises each container like the server does", () => {
    expect(sniffAudio(WAV)).toBe("wav");
    expect(sniffAudio(MP3_ID3)).toBe("mp3");
    expect(sniffAudio(MP3_SYNC)).toBe("mp3");
    expect(sniffAudio(FLAC)).toBe("flac");
    expect(sniffAudio(OGG)).toBe("ogg");
    expect(sniffAudio(M4A)).toBe("m4a");
    expect(sniffAudio(bytes("hello world"))).toBeNull();
    expect(sniffAudio(new Uint8Array())).toBeNull();
  });

  it("rejects a renamed file and non-audio content", () => {
    expect(checkImportHead("wav", WAV)).toMatchObject({ ok: true });
    const renamed = checkImportHead("mp3", WAV);
    expect(!renamed.ok && renamed.message).toMatch(/named \.mp3 but is really WAV/);
    expect(checkImportHead("mp3", bytes("just some text"))).toMatchObject({ ok: false, code: "unsupported_format" });
  });
});

describe("validateImportFile", () => {
  it("passes a real WAV header and fails a .txt renamed to .wav before upload", async () => {
    await expect(validateImportFile(new File([WAV, new Uint8Array(100)], "loop.wav", { type: "audio/wav" }))).resolves.toMatchObject({ ok: true, ext: "wav" });
    await expect(validateImportFile(new File(["plain text, not audio"], "fake.wav", { type: "" }))).resolves.toMatchObject({ ok: false, code: "unsupported_format" });
  });
});
