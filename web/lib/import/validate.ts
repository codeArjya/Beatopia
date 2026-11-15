// Client-side checks for desktop imports (T7.1). They mirror the API's own rules (WS2 `app/core/imports.py`)
// so a bad file is rejected before a 25 MB upload: extension allow-list, 25 MiB limit, non-empty, and the
// same magic-byte sniff. The server still checks everything; this only saves the round trip.

export const IMPORT_EXTENSIONS = ["wav", "mp3", "flac", "m4a", "ogg"] as const;
export type ImportExt = (typeof IMPORT_EXTENSIONS)[number];

/** Same as the server's MAX_UPLOAD_BYTES (25 × 1024 × 1024). */
export const MAX_IMPORT_BYTES = 25 * 1024 * 1024;

/** For `<input accept>`: extensions plus the MIME types browsers report for them. */
export const IMPORT_ACCEPT = ".wav,.mp3,.flac,.m4a,.ogg,audio/*";

export type ImportCheck =
  | { ok: true; ext: ImportExt }
  | { ok: false; code: "unsupported_format" | "upload_too_large" | "empty_file"; message: string };

export type FileMeta = { name: string; size: number; type: string };

export function fileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot <= 0 || dot === name.length - 1 ? "" : name.slice(dot + 1).toLowerCase();
}

const isImportExt = (ext: string): ext is ImportExt => (IMPORT_EXTENSIONS as readonly string[]).includes(ext);

/**
 * MIME types that are fine for an audio file. Browsers often report "" (unknown) or octet-stream, and use
 * video/* for .ogg/.m4a containers, so only a clearly non-audio type (text/plain, image/png, application/pdf…)
 * is rejected.
 */
function mimeLooksAudio(type: string): boolean {
  const t = type.toLowerCase().split(";")[0].trim();
  return (
    t === "" ||
    t.startsWith("audio/") ||
    t === "application/octet-stream" ||
    t === "application/ogg" ||
    t === "video/ogg" ||
    t === "video/mp4"
  );
}

export function formatMB(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return `${mb >= 10 ? Math.round(mb) : mb.toFixed(1).replace(/\.0$/, "")} MB`;
}

/** Name, size and MIME checks (no file read). */
export function checkImportMeta({ name, size, type }: FileMeta): ImportCheck {
  const ext = fileExtension(name);
  if (!isImportExt(ext)) {
    return {
      ok: false,
      code: "unsupported_format",
      message: `${ext ? `.${ext} files aren't` : "That file isn't"} supported. Use WAV, MP3, FLAC, M4A or OGG.`,
    };
  }
  if (!mimeLooksAudio(type)) {
    return { ok: false, code: "unsupported_format", message: `That file doesn't look like audio (${type}).` };
  }
  if (size === 0) return { ok: false, code: "empty_file", message: "That file is empty." };
  if (size > MAX_IMPORT_BYTES) {
    return {
      ok: false,
      code: "upload_too_large",
      message: `That file is ${formatMB(size)}. The limit is ${formatMB(MAX_IMPORT_BYTES)}; trim or compress it first.`,
    };
  }
  return { ok: true, ext };
}

/** Container type from the first bytes (same rules as the server's `sniff`), or null. */
export function sniffAudio(head: Uint8Array): ImportExt | null {
  const ascii = (from: number, to: number) => String.fromCharCode(...head.subarray(from, to));
  if (ascii(0, 4) === "RIFF" && ascii(8, 12) === "WAVE") return "wav";
  if (ascii(0, 4) === "fLaC") return "flac";
  if (ascii(0, 4) === "OggS") return "ogg";
  if (ascii(4, 8) === "ftyp") return "m4a";
  if (ascii(0, 3) === "ID3" || (head.length > 1 && head[0] === 0xff && (head[1] & 0xe0) === 0xe0)) return "mp3";
  return null;
}

/** Content check against the declared extension; mirrors the server's `check_format`. */
export function checkImportHead(ext: ImportExt, head: Uint8Array): ImportCheck {
  const kind = sniffAudio(head);
  if (kind === null) {
    return { ok: false, code: "unsupported_format", message: "That file doesn't look like audio (WAV, MP3, FLAC, M4A or OGG)." };
  }
  if (kind !== ext) {
    return {
      ok: false,
      code: "unsupported_format",
      message: `That file is named .${ext} but is really ${kind.toUpperCase()}. Rename it to .${kind} and try again.`,
    };
  }
  return { ok: true, ext };
}

/** Full client check: meta first (no read), then the first 16 bytes. */
export async function validateImportFile(file: File): Promise<ImportCheck> {
  const meta = checkImportMeta(file);
  if (!meta.ok) return meta;
  const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  return checkImportHead(meta.ext, head);
}
