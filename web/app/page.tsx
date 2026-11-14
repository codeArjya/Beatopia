import { Suspense } from "react";

import { SearchPage, SearchPageSkeleton } from "@/components/search/SearchPage";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col">
      <Suspense fallback={<SearchPageSkeleton />}>
        <SearchPage />
      </Suspense>
    </main>
  );
}
