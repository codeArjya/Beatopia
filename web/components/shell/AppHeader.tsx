import { AudioLinesIcon, UploadIcon } from "lucide-react";
import Link from "next/link";

import { AppButton } from "@/components/adapters";
import { SEARCH_SECTION_ID } from "@/components/hero/config";

import { SkipLink } from "./SkipLink";

/** Top bar on every route: logo → home (intro), Search → the search section, Import → /import. Pages render their own <main> below it. */
export function AppHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/70">
      <SkipLink />
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2 rounded-md text-[17px] font-extrabold tracking-tight focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <AudioLinesIcon className="size-5 text-primary-strong" aria-hidden />
          Beatopia
        </Link>
        <p className="hidden text-sm text-text-secondary sm:block">Find a sample, hear it loop, flip it.</p>
        <nav aria-label="Main" className="ml-auto flex items-center gap-2">
          <AppButton asChild variant="ghost" size="sm">
            {/* Straight to the search, past the intro (the logo goes to the top of the page). */}
            <Link href={`/#${SEARCH_SECTION_ID}`}>Search</Link>
          </AppButton>
          <AppButton asChild variant="outline" size="sm">
            <Link href="/import">
              <UploadIcon aria-hidden />
              Import
            </Link>
          </AppButton>
        </nav>
      </div>
    </header>
  );
}
