import { Suspense } from "react";

import { HERO, SEARCH_SECTION_ID } from "@/components/hero/config";
import { HeroSection } from "@/components/hero/HeroSection";
import { CoversProvider } from "@/components/search/CoverArt";
import { SearchPage, SearchPageSkeleton } from "@/components/search/SearchPage";
import { publicAsset } from "@/lib/assets/public";
import { COVER_FILES } from "@/lib/search/cover";

/**
 * Home: the scroll hero, then the search page as its continuation. The search section fills at least one
 * screen, so "Start digging" (and /#search) can bring it flush under the header.
 */
export default function Home() {
  // Optional art, switched on by adding the files to public/: hero/backdrop.jpg and covers/cover0-5.jpg.
  const backdrop = publicAsset(HERO.backdrop.image);
  const covers = COVER_FILES.filter((file) => publicAsset(file) !== null);

  return (
    <main className="flex flex-1 flex-col">
      <HeroSection backdropSrc={backdrop} />
      <div id={SEARCH_SECTION_ID} className="flex min-h-[calc(100svh_-_3.5rem)] flex-1 scroll-mt-14 flex-col">
        <CoversProvider covers={covers}>
          <Suspense fallback={<SearchPageSkeleton />}>
            <SearchPage />
          </Suspense>
        </CoversProvider>
      </div>
    </main>
  );
}
