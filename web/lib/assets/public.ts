import { existsSync } from "node:fs";
import path from "node:path";

/**
 * Server only. Returns `src` if that file exists in public/, else null. Used for optional art that is dropped
 * in later (the hero backdrop, sample covers): the page turns it on by itself once the file is there, and
 * never requests a file that is missing.
 */
export function publicAsset(src: string): string | null {
  return existsSync(path.join(process.cwd(), "public", src)) ? src : null;
}
