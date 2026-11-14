import Link from "next/link";

import { AppButton } from "@/components/adapters";
import { PillDemo } from "@/components/search/PillDemo";

// Stub: the search page (chip tray, search bar, results) replaces this from T2.x on.
export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-6 px-4 py-24 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight">Find your next sample</h1>
      <p className="text-muted-foreground">
        Search goes here. The API client serves fixtures when{" "}
        <code className="font-mono text-sm">NEXT_PUBLIC_USE_FIXTURES=1</code>.
      </p>
      <PillDemo />
      <div>
        <AppButton asChild>
          <Link href="/editor?track=jam_1532881&start=0&end=10.667&stem=mix">Open the editor on a fixture</Link>
        </AppButton>
      </div>
    </main>
  );
}
