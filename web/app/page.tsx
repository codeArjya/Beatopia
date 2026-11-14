import Link from "next/link";

import { Button } from "@/components/ui/button";

// Placeholder search page (WS3 builds the real one).
export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-6 px-6 py-24">
      <h1 className="text-3xl font-semibold tracking-tight">Beatopia</h1>
      <p className="text-muted-foreground">
        Sample search goes here (WS3). The bootstrap API client serves fixtures when{" "}
        <code className="font-mono text-sm">NEXT_PUBLIC_USE_FIXTURES=1</code>.
      </p>
      <div>
        <Button asChild>
          <Link href="/editor?track=jam_1532881&start=0&end=10.667&stem=mix">Open the editor on a fixture</Link>
        </Button>
      </div>
    </main>
  );
}
