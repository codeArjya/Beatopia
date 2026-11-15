"use client";

import { WifiOffIcon } from "lucide-react";

import { offlineToggleHref } from "@/lib/api";
import { useDataMode } from "@/lib/api/useOffline";

/**
 * Shown on every page while the `?offline=1` backup demo is on: the library comes from bundled fixtures. "Go live"
 * reloads the page with `?offline=0` (the API client picks its mode once per page load).
 */
export function StatusBanner() {
  const { offline } = useDataMode();
  if (!offline) return null;
  return (
    <div role="status" className="border-b border-border bg-secondary">
      <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-2 text-sm sm:px-6">
        <WifiOffIcon className="size-4 shrink-0 text-warning" aria-hidden />
        <p className="flex-1 text-text-secondary">
          <span className="font-semibold text-foreground">Offline demo.</span> Searching a small bundled library; nothing is
          sent to the server.
        </p>
        <a
          href="?offline=0"
          onClick={(e) => {
            e.preventDefault();
            window.location.assign(offlineToggleHref(window.location.href, false));
          }}
          className="rounded-full px-3 py-1 font-semibold text-primary-strong hover:bg-accent focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          Go live
        </a>
      </div>
    </div>
  );
}
