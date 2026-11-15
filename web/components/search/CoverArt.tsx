"use client";

import Image from "next/image";
import { createContext, useContext, type ReactNode } from "react";

import { pickCover } from "@/lib/search/cover";
import type { Result } from "@/lib/types/api";

const CoversContext = createContext<readonly string[]>([]);

/** Hands the list of cover files that exist in public/covers (checked on the server) to the result cards. */
export function CoversProvider({ covers, children }: { covers: readonly string[]; children: ReactNode }) {
  return <CoversContext value={covers}>{children}</CoversContext>;
}

/**
 * Small square cover on a sample tile. Decorative (the title next to it names the track), so it has an empty
 * alt. Renders nothing until cover files exist, which keeps the card exactly as it was without them.
 */
export function CoverArt({ result }: { result: Result }) {
  const covers = useContext(CoversContext);
  const src = pickCover(result, covers);
  if (!src) return null;
  return (
    <Image
      src={src}
      alt=""
      width={44}
      height={44}
      sizes="44px"
      className="size-11 shrink-0 rounded-(--radius-art) object-cover shadow-art"
    />
  );
}
