"use client";

import { usePathname } from "next/navigation";

/** The search text input's id (components/search/SearchBar). */
export const SEARCH_INPUT_ID = "search-text";

/**
 * First tab stop on the search page: jumps past the header and the ~150-chip tray straight to the search box
 * (Tab from there reaches the results). Hidden until focused.
 */
export function SkipLink() {
  const pathname = usePathname();
  if (pathname !== "/") return null;
  return (
    <a
      href={`#${SEARCH_INPUT_ID}`}
      onClick={(e) => {
        const input = document.getElementById(SEARCH_INPUT_ID);
        if (!input) return;
        e.preventDefault();
        input.focus();
      }}
      className="sr-only rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50"
    >
      Skip to search
    </a>
  );
}
