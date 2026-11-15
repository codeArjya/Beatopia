import { AudioLinesIcon, UploadIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

/** Top bar on every route: logo → search (home), Import → /import. Pages render their own <main> below it. */
export function AppHeader() {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2 rounded-md text-[17px] font-extrabold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <AudioLinesIcon className="size-5" aria-hidden />
          Beatopia
        </Link>
        <p className="hidden text-sm text-muted-foreground sm:block">Find a sample, hear it loop, flip it.</p>
        <nav aria-label="Main" className="ml-auto flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href="/">Search</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/import">
              <UploadIcon aria-hidden />
              Import
            </Link>
          </Button>
        </nav>
      </div>
    </header>
  );
}
