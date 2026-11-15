"use client";

import { useEffect, useState } from "react";

/**
 * True once `active` has stayed true for `ms` without `key` changing. Goes back to false as soon as `active`
 * turns false or `key` changes (a new request starts its own clock).
 */
export function useSlow(active: boolean, key: string, ms: number): boolean {
  const [slowKey, setSlowKey] = useState<string | null>(null);
  useEffect(() => {
    if (!active) return;
    const t = setTimeout(() => setSlowKey(key), ms);
    return () => clearTimeout(t);
  }, [active, key, ms]);
  return active && slowKey === key;
}
