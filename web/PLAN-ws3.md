# PLAN: WS3 web shell & search UX

Branch `ws3-web`. Edit scope: `web/` except `web/app/editor/`, `web/components/editor/`, `web/lib/audio/`, `web/stores/`.
Status: **approved; building.** Rebased on `main` after the `contract:` PR (cb05f68): typed `Job.output`, `search_empty`/`search_fallback` fixtures, and the fallback / import / score rules are now real.
Open-question answers were taken as the defaults written below (loop until stopped, search state in the URL, lazy why fetch, dark-only until H16).

## 0. What I checked (H0)

`pnpm install --frozen-lockfile` is done. `pnpm test` passes 7/7, and `pnpm typecheck` and `pnpm lint` are clean on the bootstrap.

| Package | Installed | API facts that shape this plan |
| --- | --- | --- |
| next | 16.4.6 | `cacheComponents: true` is on. A client component that calls `useSearchParams` must sit inside a `<Suspense>` boundary, or prerendering fails. I'll read `node_modules/next/dist/docs/` before touching routing or layout (see `web/AGENTS.md`). Typed `LayoutProps<"/">` is already used. |
| react | 19.3.0 | `useSyncExternalStore` is available for the shared preview player. |
| @dnd-kit/core | 6.3.1 | `DndContext`, `useDraggable`, `useDroppable`, `DragOverlay`, `PointerSensor` (with `activationConstraint: { distance }`), `KeyboardSensor`, and screen-reader `announcements`. |
| @dnd-kit/sortable | 10.0.0 | `SortableContext`, `useSortable`, `horizontalListSortingStrategy`, `sortableKeyboardCoordinates`, `arrayMove`. |
| @dnd-kit/utilities | 3.2.2, transitive only | **Not a direct dependency.** I won't import it. I'll write the transform string by hand, so no `[dep]` is needed. |
| @tanstack/react-query | 5.107.1 | `queryOptions()`, `keepPreviousData` (passed as `placeholderData`), `skipToken`, and `refetchInterval: (query) => number \| false`. |
| wavesurfer.js | 7.12.12 | Accepts precomputed `peaks`. **WS3 won't use it.** Mini-waveforms are drawn on a plain canvas, as §9 of the handoff asks. Only WS4 uses wavesurfer. |
| shadcn (CLI) | 4.23.0 | `new-york` style. Components import the unified `radix-ui` package (`Dialog as SheetPrimitive`) and use `cn` from the `cn` package. Already installed: button, badge, card, dialog, input, scroll-area, sheet, slider, sonner, tabs, tooltip. I may add `skeleton`, `progress` and `collapsible` with `pnpm dlx shadcn add`; that generates code, not dependencies. |

## 1. Decisions (final)

| Decision | Final answer | Change from the default |
| --- | --- | --- |
| **Routing** | `/` is search (home), `/import` is the drop zone, `/editor` belongs to WS4. Header: logo (link to `/`), search hint, Import button. The root layout renders the header; **each page renders its own `<main>`** (WS4's editor page already does, so a layout `<main>` would nest landmarks). | **Addition:** search state goes in the URL: `/?q=dusty+keys&chips=genre.soul,inst.keys`. It's updated with `router.replace`, debounced. **Reason:** after "Open in editor", the browser Back button must bring back the same search, and a URL is also an easy way to reset the demo. The page reads params in a client component inside `<Suspense>`, as cacheComponents requires. |
| **Chip UX** | The left tray is grouped by category from `useChips()`. Each group is collapsible, and a small filter box narrows the 60 instrument chips. A chip is added by **click** or by **dragging** it onto the search bar. Stacked chips show as removable pills before the text, and **pills can be reordered** by drag, because `SearchRequest.chips` order is the stacking order. Backspace on empty text removes the last pill. Search runs 300 ms after any change. With no text and no chips, no search runs and the idle state shows. Adding the same chip twice does nothing. | Keep. Mechanics: one `DndContext` wraps the tray and the bar. Tray chips use `useDraggable`, the bar uses `useDroppable`, and pills sit in a `SortableContext` with `horizontalListSortingStrategy`. `PointerSensor` uses `distance: 4` so a click still counts as a click. `KeyboardSensor` uses `sortableKeyboardCoordinates`, and `DragOverlay` shows the dragged chip. |
| **Chip colors** | `ChipCategory.color` holds the CSS variable name. Pills use `background: color-mix(in oklch, var(--chip-x) 18%, transparent)`, `border-color: var(--chip-x)`, with text in the foreground color. The tray uses the same style at a lower tint. | Keep. |
| **Result card** | Mini waveform of the window (static canvas with a playhead overlay), title + artist (truncated, full text in `title=`), BPM / key / bars in monospace with `tabular-nums` ("—" when null), top 3 tags, license badge, collapsible why note, and the buttons Play, Stems, Open in editor. | **Change:** the attribution also shows as a one-line muted caption, and the badge tooltip shows the full text. **Reason:** AGENTS.md says "the UI always shows" license and attribution, and a tooltip alone hides it. |
| **Mini waveform** | `lib/waveform/`: fetch, then `decodeAudioData` on one lazily created `AudioContext`. Decoding doesn't need a user gesture. The decoded buffer is cached per `audio_url`, because all fixtures share `mix.wav` and real windows share each track's `mix.mp3`. Peaks are computed for `[start_s, end_s]` only, 96 buckets, and cached through TanStack Query (`["peaks", url, start, end]`, `staleTime: Infinity`). Decoding starts only when the card scrolls into view (IntersectionObserver), at most 2 at a time. If decoding fails (CORS or a bad file), a flat placeholder shows and the card still works. | Keep (the canvas is the default). |
| **Preview audio** | One `HTMLAudioElement` for the whole app, owned by `PreviewProvider` in `lib/preview/`. It isn't a Zustand store, because `web/stores/` belongs to WS4. Components subscribe with `useSyncExternalStore`. `play(item)` sets `src` (only if it changed), seeks to `start_s`, and plays. A `requestAnimationFrame` loop checks `currentTime >= end_s` and jumps back to `start_s`, because `timeupdate` fires only about every 250 ms and overshoots. Looping continues until the user stops it or another preview starts. Hovering or focusing a card warms the cache with `preload="auto"` (on the shared element only when it's idle). Space toggles play on the focused card, never while focus is in a text input. With `cacheComponents`, Next hides left routes with React `<Activity>` instead of unmounting them, so the search page stops the preview in a `useLayoutEffect` cleanup (runs when it's hidden) and on "Open in editor". | Keep. **Interpretation to confirm:** I read "loops while held" as "loops while it's the active preview". |
| **Stems drawer** | shadcn `Sheet` with `side="right"`, wrapped as `AppSheet`. On open it calls `useStems(trackId, {start_s, end_s})`, a query rather than a mutation (see State). If `stems` comes back, they render right away. If `job_id` comes back, `useJob` polls every 1 s and shows a progress bar and status, then reads `output.stems` (typed `StemsJobOutput`, narrowed with `"stems" in output`). For a Freesound fallback result (`fs_*` not in the DB) the first stems request makes the API store a minimal track row and always queues a job, so expect the job path there. There's one row per stem actually returned (4 for `htdemucs`, 6 for `htdemucs_6s`): Play (soloed through the shared preview player, at an offset of `start_s - range_start_s` inside the stem file) and "Use in editor". Errors show inline with a Retry button. A range longer than 60 s is clamped on the client to 60 s, so `range_too_long` never happens. | Keep. "Solo" means playing that stem alone. **No** simultaneous multi-stem mixer in the drawer. |
| **StemsDrawer API (for WS4)** | `<StemsDrawer trackId startS endS open onOpenChange onPick? />`. Without `onPick`, "Use in editor" navigates to `/editor?track=…&start=…&end=…&stem=…`. WS4 passes `onPick(stem: Stem)` to add a clip instead. | New, needed by WS4. |
| **Import** | On `/import`: a drop zone that is also a click-to-browse `<input type=file>`. The client checks the extension and size (≤ 25 MB) before upload. Then `useImport` (a mutation) runs, then `useJob` polls the analyze job, then a summary shows (title, duration, BPM, key, window count) with "Open in editor". The editor link uses the window with the highest `loopability`, or `0 → min(duration, 8 bars)` when there are no windows. On `done`, `output.track` (typed `AnalyzeJobOutput`) is written into `["track", track_id]` so the editor opens with no extra request. Imported tracks are private (never in `/search`), so the summary page is the only way back to them. | Keep. |
| **State** | TanStack Query for all server data. Query keys live in `lib/api/keys.ts`: `["chips"]`, `["search", {text, chips, limit}]`, `["track", id]`, `["stems", trackId, start, end, model]`, `["job", id]`, `["why", windowId]`, `["peaks", url, start, end]`. **`session_id` isn't part of any key.** It's read from localStorage inside `queryFn`/`mutationFn`, never during render, so the server and client HTML can't mismatch. Search uses `placeholderData: keepPreviousData` so old results stay on screen while the next search loads. `useStems` is a query with `retry: false` and `staleTime: Infinity`, so a retry can't queue a second separation job. `useJob` uses `refetchInterval: q => done/error ? false : 1000`. Local UI state stays in components, and preview state lives in `PreviewProvider`. | Keep. Adds `useStems` as a query and the `skipToken` idle search. |
| **Empty / error states** | Skeleton cards on the first load, and a dimmed list during a refetch. Zero results shows "No matches, try fewer chips" with a one-click "Remove last chip" (even when `fallback_used` is true, as in `search_empty.json`). When `fallback_used` is true and there are results, a banner says "Expanded to Freesound" (trivial, so it lands with Results rather than in Tier 2). For `ApiError` codes: `rate_limited` and `upstream_error` show an inline retry plus a sonner toast. `network_error` shows a banner, which will later link to `?offline=1`. | Keep. |
| **Adapters layer** | `components/adapters/`: `AppButton`, `AppCard`, `AppSheet`, `Pill` (category-colored, optional remove button, forwards dnd refs and listeners), `LicenseBadge`, `MonoStat`. Feature components import only adapters, never `components/ui/*` directly. | Keep. |
| **Accessibility** | Every chip is a `<button>`, and a click is the alternative to dragging. dnd-kit `announcements` read out "Added Soul to search". Every card is a focusable `<article tabIndex=0>` labelled by its title, with Space/Enter to play. The results count is announced in an `aria-live="polite"` region. The drawer gets focus trapping from Radix. Visible focus rings are kept. | Keep. |
| **Theme** | Dark by default (`class="dark"` on `<html>`) from H0. The H16 token pass may add a toggle through `next-themes`, which is already installed. | Fills a gap: the brief asks for "dark theme polish". |

## 2. Needs from other streams

| From | Need | By | Assumption until then |
| --- | --- | --- | --- |
| WS2 | Add the Vercel production + preview URLs to `WEB_ORIGIN` (now a comma-separated list per the contract) | H12 | Fixture mode. I'll send the URLs as soon as the project exists. |
| WS2 | Production API URL | H12 | `NEXT_PUBLIC_API_URL=http://localhost:8000`. |
| WS2 | `GET /tracks/{id}` returns **every** stem row, including range stems. WS4 needs this to resolve `?stem=` on the hand-off URL. | H12 | Yes. I'll confirm with WS2 and WS4. Also passed to WS4 as a note. |
| WS2 | Error bodies are always `{"error": {code, message}}`, including 422 validation errors | H12 | Anything else maps to `http_error`, which the bootstrap client already does. |
| WS1 | The Supabase `audio` bucket answers `fetch` with `Access-Control-Allow-Origin`. Mini-waveforms need this; `<audio>` playback doesn't. | H12 | Public buckets usually allow it. If not, the waveform falls back to the placeholder and nothing else breaks. |
| WS2 | Optional: run the API with `USE_FIXTURES=1` so I can test real HTTP (CORS, error bodies) before the DB is ready | H8 | Web fixture mode only. |
| WS1 / WS2 | The chip vocabulary stays frozen after H12 (`/chips`), so chip ids in shared URLs keep working | H12 | Unknown chip ids in the URL are silently dropped. |
| WS4 | Confirm the hook signatures in §3 T1.2 (`useTrack(id)`, `useStems(trackId, req)`, `useJob(id)`, `useAssist()` as a mutation) and the `StemsDrawer` props | H4 | As written in this plan. |
| WS4 | The editor page reads `track/start/end/stem` and doesn't depend on any WS3 state | H4 | Yes (the URL is fixed by the handoff). |
| Human (P3) | Claude Design tokens in `docs/proposals/WS3-design-tokens.md` | H16 | Bootstrap neutral palette + placeholder `--chip-*` colors. |
| Human | Vercel project access and env vars (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_USE_FIXTURES=0`) | H12 | Local only. |

## 3. Contract changes

Landed in cb05f68 (no open proposals from WS3):
1. **Typed job output**: `Job.output` is `StemsJobOutput | AnalyzeJobOutput | null`. No runtime guards needed; code narrows with `"stems" in output` / `"track" in output`.
2. **Search fixtures**: `search_empty.json` (0 results, `fallback_used: true`) and `search_fallback.json` (3 low-score results, a Freesound track, null bpm/key/artist, a long title). The dev-only `?fixture=empty|fallback` switch in fixture mode loads them directly; tests use them as-is.
3. **Window ids are opaque**: the contract now says clients read `start_s`/`end_s` and never parse `window_id`. WS3 already planned that.

Other contract facts this plan now relies on: fallback windows are `0..min(duration,16)` s with a Freesound preview `audio_url`; `GET /tracks/fs_*` and `POST /why` work for fallback results live; `WEB_ORIGIN` is a list.

## 4. Task list (1–2 h tasks, acceptance checks, gates)

Checks after every task: `pnpm lint && pnpm typecheck && pnpm test`. After each gate I also walk through the flow in Chrome and list the tested steps in the PR description.
The vitest environment is `node`, and I'm **not** adding jsdom or testing-library. Tests cover pure functions and `queryOptions` factories (run with `queryClient.fetchQuery`). UI is checked by hand in Chrome.

### Shell, H0 → **Gate H4** (merge so WS4 can rebase)
- [x] **T1.1 Layout + routes** (1 h). Read the Next 16 docs on layouts, client components and cacheComponents. Root layout with a header (logo, Import button), dark theme, `<main>` slot. `/import` stub page. `/` stub with the existing editor link kept.
  *Accept:* `/`, `/import`, `/editor?track=jam_1532881&start=0&end=10.667&stem=mix` all render under the header with no console errors. `pnpm build` passes.
- [x] **T1.2 `lib/api` hooks for every endpoint** (1.5 h). `lib/api/keys.ts`, `lib/api/queries.ts` (`chipsQuery`, `searchQuery`, `trackQuery`, `stemsQuery`, `jobQuery`, `whyQuery`), `lib/api/hooks.ts` (`useHealth`, `useChips`, `useSearch`, `useTrack`, `useStems`, `useJob`, `useWhy`, `useImport`, `useSeedTrackFromJob`, `usePostEvent`, `useAssist`), `jobStems`/`jobTrack` output accessors, the `?fixture=empty|fallback` switch in the fixture client, `lib/session.ts` (`getSessionId()`, SSR-safe), and `lib/api/index.ts` barrel.
  *Accept:* Vitest in fixture mode covers each query factory (search → 8, chips → 5 categories, job polling interval 1000 → false once done), typed `output` narrowing on both done fixtures, and `getSessionId` being stable across calls.
- [x] **T1.3 Adapters + tokens skeleton** (1 h). `AppButton`, `AppCard`, `AppSheet`, `Pill`, `LicenseBadge`, `MonoStat`. `--chip-*` tints wired in `globals.css`.
  *Accept:* a temporary `/` demo row shows one pill per category in its color, and keyboard focus is visible.
- [x] **Gate H4:** open a PR `feat(ws3): app shell + lib/api hooks` and tell the human it's ready for WS4.

### Chip tray + search bar, H2 → H5
- [x] **T2.1 Search state** (1 h). `lib/search/state.ts` is a pure reducer (`add` dedupes, `remove`, `removeLast`, `reorder`, `setText`). `useSearchState` syncs with the URL (Suspense-wrapped) and returns a 300 ms debounced `SearchRequest` (or `null` when empty).
  *Accept:* unit tests for the reducer, URL parsing/serializing, and unknown chip ids being dropped. Back/forward restores the search.
- [x] **T2.2 ChipTray** (1.5 h). Grouped and collapsible categories, a filter box, click to add. Chips already in the search look selected.
  *Accept:* all 5 fixture categories render, clicking adds a pill, Tab reaches every chip, and Enter adds it.
- [x] **T2.3 SearchBar + drag-and-drop** (2 h). Pills before the text input, Backspace removes the last pill, `DndContext` covers drag from tray to bar, sortable pills, and `DragOverlay`, plus announcements.
  *Accept (manual):* drag Soul, Keys, then Melancholy into the bar, reorder them, and see the URL `chips=` order change. A click still adds a chip without starting a drag. Keyboard drag works (Space, arrows, Space).
- [x] **T2.4 Wire search** (0.5 h). `useSearch(req ?? skipToken)` with `keepPreviousData`, and an idle state when the request is null.
  *Accept:* each pause after typing causes exactly one request (checked with a console counter). The list doesn't flash while a new search loads.

### Results, H5 → **Gate H8** (full search flow on fixtures)
- [x] **T3.1 PreviewProvider** (1.5 h). Shared `<audio>`, `play/stop/toggle`, loop at `end_s` checked with rAF, state exposed with `useSyncExternalStore`, warm-up on hover.
  *Accept:* unit test for the pure loop-boundary helper. Manually: sound within 1 s of a click, only one preview at a time, loops cleanly at the window end.
- [x] **T3.2 ResultCard + ResultList** (2 h). Meta row in monospace, top 3 tags, license badge + attribution caption, skeletons, the empty state with "Remove last chip", the fallback banner, error states, and the `aria-live` count.
  *Accept:* the 8 fixture cards render. `?fixture=empty` (`search_empty.json`) and `?fixture=fallback` (`search_fallback.json`) show their states. A null key or bpm shows "—". Long titles truncate.
- [x] **T3.3 MiniWaveform** (1.5 h). `lib/waveform/peaks.ts` (pure: buffer + range → 96 peaks), a decode cache, the concurrency limit of 2, an IntersectionObserver trigger, canvas drawing at the device pixel ratio, and a playhead overlay from the preview state.
  *Accept:* unit test for peaks (known sine, correct bucket count, values in [0,1]). On the page, 8 waveforms with `mix.wav` decoded once (network tab). A decode failure shows the placeholder.
- [x] **T3.4 Editor hand-off + keyboard** (0.5 h). `lib/links.ts` `editorHref({track,start,end,stem})`, the "Open in editor" button, and Space/Enter on a focused card.
  *Accept:* unit test for `editorHref`. Clicking opens WS4's route with the right params, and Back restores the search.
- [x] **Gate H8:** walk through stack chips → hear a window → open in editor on fixtures, then open a PR `feat(ws3): search flow` (PR #4, stacked on #3).

### Why notes, H8 → H9
- [ ] **T4.1 WhyNote** (1 h). `useWhy(windowId, { initialData: result.why, enabled })`. Collapsed to 2 lines and expandable. When `why` is null, the fetch happens on first expand **or** first play (no fetch-on-scroll, to save Gemini calls). Loading shimmer, inline retry on error.
  *Accept:* on fixtures, the 2 results with `why: null` show a shimmer and then the note. Cached notes show with no request.

### Stems drawer, H9 → H12
- [ ] **T5.1 StemsDrawer data flow** (1.5 h). The `useStemsFlow(trackId, start, end)` hook handles both the ready path and the job path, returns `{status, progress, stems, error, retry}`, clamps to 60 s, and invalidates `["track", id]` when the job is done.
  *Accept:* in fixture mode, `jam_1532881` with 0–10.667 is ready at once, and a range past 16 s goes queued → running (2 polls) → done.
- [ ] **T5.2 StemsDrawer UI** (1.5 h). Sheet, progress bar, one row per stem with Play (solo, offset-aware) and "Use in editor", `onPick` for WS4.
  *Accept:* unit test for the stem offset math. Manually: each stem plays its matching segment, and "Use in editor" opens `…&stem=drums`. Esc closes and returns focus to the Stems button.

### Go live + deploy, H12 → H14 (together with WS2)
- [ ] **T6.1 Live API** (1.5 h). `NEXT_PUBLIC_USE_FIXTURES=0` and fix what real data breaks: long titles, missing bpm or key, no results, slow searches (> 3 s spinner text), CORS on the waveform fetch.
  *Accept:* 5 real queries render without layout breaks. Fixture mode still passes the H8 walkthrough.
- [ ] **T6.2 Vercel deploy** (1 h). Project rooted at `web/`, env vars set, production URL sent to the human, CORS confirmed with WS2.
  *Accept:* the production URL runs a live search with no CORS errors in the console.

### Import, H14 → **Gate H16** (Tier 0 in production)
- [ ] **T7.1 ImportDropzone** (1 h). Drag-and-drop or click-to-browse, the client-side checks (`lib/import/validate.ts`), and upload through `useImport`.
  *Accept:* unit tests for extension, size and MIME edge cases. A 30 MB file or a `.txt` is rejected before upload with a clear message.
- [ ] **T7.2 Analyze polling + summary** (1 h). Progress, a summary of the `TrackDetail`, the `["track", id]` cache seeded, and "Open in editor" using the best window.
  *Accept:* fixture import → done → summary shows 90 BPM, A minor, and the editor opens. Live: upload a real 10 s WAV in production.
- [ ] **Gate H16:** in production, stack Soul + Keys + Melancholy → hear it → read the why note → open stems → send to the editor, and import → editor.

### Design pass, H16 → **Gate H20**
- [ ] **T8.1 Apply the Claude Design tokens** (1.5 h) through `globals.css` and the adapters only.
  *Accept:* before and after screenshots of `/` and the stems drawer. No feature component edited for colors.
- [ ] **T8.2 Typography + motion** (1.5 h). Grotesk UI (Geist) with monospace `tabular-nums` numbers, a chip snap animation (dnd-kit `dropAnimation`), and a result fade/shuffle of at most 200 ms in CSS only, with no new dependency. `prefers-reduced-motion` is respected.
  *Accept:* the animations don't delay audio start, and reduced motion turns them off.
- [ ] **T8.3 Dark polish + a11y sweep** (1 h). Contrast of chip tints on dark, focus rings, keyboard-only run of the whole flow.
  *Accept:* the flow is doable without a mouse, and chip text contrast is ≥ 4.5:1.
- [ ] **Gate H20:** design pass merged, screenshots in the PR.

### Tier 2 (H20+, in cut-list order)
- [ ] **T9.1 Events** (1 h). `usePostEvent` fire-and-forget for `play` (first play per card per query), `pick` (open in editor or use stem), and `skip` (another card played within 1.5 s of starting this one).
- [ ] **T9.2 Offline backup** (1 h). `?offline=1` switches `lib/api` to fixtures at runtime and is kept in `sessionStorage`.
- [ ] **T9.3 "Flip this sample" tips** (1.5 h), drawn from the why note.
- [ ] **T9.4 Keyboard shortcuts** (1 h). `/` focuses search, `j`/`k` move between cards, `s` opens stems, `e` opens the editor, `?` shows help.

**Cut order if behind** (handoff §10): Tier 2 → motion → import page → why lazy fetch (cached notes only) → drag-and-drop (click-to-add stays).

## 5. Component tree: search page (`/`)

```text
app/layout.tsx  (server)
└─ <Providers>                       app/providers.tsx (client): QueryClient, Tooltip, Toaster, PreviewProvider
   ├─ <AppHeader>                    components/shell/AppHeader       logo → /, <ImportButton> → /import
   ├─ <OfflineBanner?>               components/shell/StatusBanner    network_error / ?offline=1
   └─ <main>
      └─ app/page.tsx  (server)
         └─ <Suspense fallback={<SearchPageSkeleton/>}>
            └─ <SearchPage>          components/search/SearchPage (client; useSearchState → URL)
               └─ <DndContext sensors announcements onDragEnd>
                  ├─ <ChipTray>                       components/search/ChipTray (useChips)
                  │  ├─ <ChipFilterInput>
                  │  └─ <ChipCategoryGroup ×5>        collapsible, color = category.color
                  │     └─ <DraggableChip ×n>         useDraggable + click → add  → <Pill>
                  ├─ <section>
                  │  ├─ <SearchBar>                   useDroppable("search-bar")
                  │  │  ├─ <SortableContext items=chipIds strategy=horizontalList>
                  │  │  │  └─ <SortablePill ×k>       useSortable → <Pill removable>
                  │  │  └─ <SearchInput>              text; Backspace-on-empty → removeLast
                  │  ├─ <FallbackBanner?>             fallback_used
                  │  ├─ <ResultsStatus>               aria-live count / loading text
                  │  └─ <ResultList>                  useSearch(req ?? skipToken), keepPreviousData
                  │     ├─ <ResultCardSkeleton ×8>    first load
                  │     ├─ <EmptyState>               "No matches, try fewer chips" + Remove last chip
                  │     ├─ <SearchError>              retry
                  │     └─ <ResultCard ×n>            <AppCard> article tabIndex=0, Space → toggle preview
                  │        ├─ <MiniWaveform>          canvas + playhead (usePeaks, usePreview)
                  │        ├─ <ResultMeta>            title/artist, <MonoStat> bpm·key·bars, tags ×3
                  │        ├─ <LicenseBadge>          tooltip = attribution, + caption line
                  │        ├─ <WhyNote>               useWhy (lazy), collapsible
                  │        └─ <ResultActions>         Play · Stems · Open in editor (editorHref)
                  └─ <DragOverlay>  → <Pill>          the chip being dragged
               └─ <StemsDrawer>                       components/search/StemsDrawer (one instance; opened per card)
                  └─ <AppSheet side="right">
                     ├─ <StemsHeader>                 track title, range, license
                     ├─ <JobProgress?>                useJob polling
                     ├─ <StemRow ×4|6>                Play (solo) · Use in editor / onPick
                     └─ <StemsError?>                 retry
```

New files I expect under `web/`: `components/{shell,search,adapters}/…`, `lib/api/{keys,queries,hooks,index}.ts`,
`lib/{session,links}.ts`, `lib/search/state.ts`, `lib/preview/{PreviewProvider.tsx,loop.ts}`, `lib/waveform/{peaks,decode}.ts`,
`lib/import/validate.ts`, `app/import/page.tsx`, and tests beside each pure module. Dependency additions planned: **none**.

## 6. Open questions

None blocking. The four review questions were resolved as the defaults in §1.

## Session log

### Session 1 (2026-11-14): T1.1–T1.3 + Gate H4
- **Done:** T1.1 shell, T1.2 `lib/api` hooks, T1.3 adapters, Gate H4 (PR #3 `feat(ws3): app shell + lib/api hooks`, https://github.com/codeArjya/Beatopia/pull/3). The branch was already on top of `origin/main` (cb05f68), so no rebase was needed. lint/typecheck clean, 25/25 tests, and `pnpm build` passes.
- **Decisions:**
  - Hook signatures as shipped for WS4: `useTrack(id|null)`, `useStems(trackId, StemsRequest|null)`, `useJob(id|null)`, `useAssist()` (mutation).
  - `PillDemo` now handles `isError`.
  - Local dev uses a git-ignored `web/.env.local` with `NEXT_PUBLIC_USE_FIXTURES=1`, because the repo-root `.env` has no `NEXT_PUBLIC_*` keys.
- **Files for next session:**
  - `lib/api/{client,keys,queries,hooks,index}.ts`
  - `lib/session.ts`, `lib/license.ts`
  - `components/adapters/*` (the `Pill` props `tone`, `color`, `onRemove` and `asChild` matter for the T2.2/T2.3 tray and bar)
  - `components/search/PillDemo.tsx` (delete it in T2.2)
  - `app/providers.tsx`, `app/layout.tsx`, `next.config.ts` (it pulls `NEXT_PUBLIC_*` from the root `.env`)
- **Known bugs / gotchas:** without `NEXT_PUBLIC_USE_FIXTURES=1` and with no API on :8000, chips fail after one retry. Search states will need real error UI in T3.2.
- **Blocked:** nothing. Waiting on PR #3 review/merge so WS4 can rebase. Next is T2.1 (search state + URL sync).

### Session 2 (2026-11-14): T2.1 + T2.2
- **Done:** T2.1 search state + URL sync, T2.2 ChipTray. The branch was already on top of `origin/main` (cb05f68). `make schema` and `make check-fixtures` passed (13 fixtures, 0 problems). lint/typecheck are clean and tests pass 39/39. I checked these by hand in Chrome on fixtures: a stale `chips=bogus.chip` is dropped from the URL; typing, toggling chips and filter+Enter update `?q=…&chips=…` after the debounce; Back from `/import` restores the search; the logo resets it, and Back/Forward across that reset both work; Tab reaches the chips in order and Enter adds one; groups collapse. No console errors.
- **Decisions:**
  - The URL is written with `window.history.replaceState`, not `router.replace`. Next 16 feeds native history calls into `useSearchParams`, and this way no RSC request runs per keystroke. Other params such as `?fixture=` are kept.
  - Local state is the source of truth. The URL follows the **debounced** state. A URL change that matches neither the debounced nor the current state counts as navigation (Back/Forward, logo link) and replaces the state. That adjustment happens during render, not in an effect.
  - Unknown chip ids are dropped once `/chips` loads. Until then, a request that has chips is held back (it's `null`), so stale ids never reach the API. If `/chips` errors, the request is sent anyway.
  - Clicking a selected tray chip **removes** it (toggle, `aria-pressed`). The reducer's `add` still dedupes. In the filter box, Enter adds the first match and Esc clears the filter. While filtering, all groups are forced open.
  - The reducer action is `move {id, overId}` (dnd-kit sortable semantics) instead of `reorder`.
  - Added the `AppInput` adapter. `Pill` with `selected` now uses a 40% tint, because 22% was barely visible against the unselected tray chips.
- **Files for next session:**
  - `lib/search/state.ts` (reducer, `parseSearchParams`/`serializeSearchParams`, `toSearchParams`, `SEARCH_LIMIT=8`)
  - `lib/search/useSearchState.ts` (returns `{state, dispatch, request}`)
  - `lib/search/chips.ts` (`indexChips`, `filterCategories`)
  - `components/search/ChipTray.tsx`. `TrayChip` is where `useDraggable` goes in T2.3.
  - `components/search/SearchPage.tsx`. It holds an **interim** search bar (pills + input + Backspace-removes-last) that T2.3 replaces with the droppable/sortable `SearchBar`, and a "Ready to search for …" placeholder that T2.4 replaces with results.
- **Known bugs / gotchas:**
  - If you click "Open in editor" less than 300 ms after an edit, the URL can still hold the previous search. Flush the debounce on hand-off in T3.4 if that matters.
  - The tray's own scroll area is only bounded at `md+`. On mobile the page scrolls instead (fine for now).
- **Blocked:** nothing. PR #3 (Gate H4) still needs review/merge. Next is T2.3 (SearchBar + drag-and-drop).

### Session 3 (2026-11-14): T2.3 + T2.4
- **Done:** T2.3 SearchBar + drag-and-drop, T2.4 search wired. lint/typecheck are clean and tests pass 47/47 (8 new in `lib/search/dnd.test.ts`). Drag-and-drop took about 1 h, well under the 2.5 h limit. I checked these by hand in Chrome on fixtures, with no console errors, including after a reload (no hydration warnings):
  - Dragging Soul, Rhodes, then Melancholy into the bar appends them. The fixture vocabulary has no "Keys" chip, so I used Rhodes.
  - Dropping Piano onto the Rhodes pill inserts it before Rhodes.
  - Dragging a pill reorders the stack, and the URL `chips=` order follows.
  - Dropping outside the bar does nothing.
  - A real mouse click on a tray chip still adds it.
  - Keyboard reorder works (Space, ←←, Space), and the live region reads "Funk moved to position 3 of 5." / "Funk dropped at position 3 of 5."
  - Two typing pauses sent exactly 2 requests (`[search] request` console counter), and the list never unmounted during a refetch.
- **Decisions:**
  - dnd-kit API checked in `node_modules` (core 6.3.1, sortable 10.0.0):
    - `KeyboardSensor` only starts a drag when `event.target === activatorNode`.
    - `PointerSensor` swallows the click (capture-phase `stopPropagation`) once a drag has activated.
  - **Tray chips drag by pointer only.** Only `listeners.onPointerDown` is passed; dnd-kit's `attributes` and `onKeyDown` are not, because they'd override `aria-pressed` and turn Enter into "pick up". The keyboard path from tray to bar is Enter/click. Stacked chips are `disabled` as draggables (clicking them removes them).
  - **Pill drag handle = the label span** (`setActivatorNodeRef`), so the × button keeps its own click/keyboard behavior and there is no nested `role=button`.
  - Drag ids: tray chips use `tray:{chipId}`, and pills use the bare chip id (the `SortableContext` items).
  - Drop rules (`dropActions`):
    - A tray chip dropped on the bar is appended. Dropped on a pill, it's inserted before that pill (`add` + `move`).
    - A pill dropped on a pill moves into its slot. Dropped on the bar's empty area, it moves to the end.
  - Collision (`searchCollision`): tray drags use `pointerWithin`, with pills ahead of the bar, so dropping anywhere else does nothing. Pill drags use `closestCenter` over pills only, which keyboard sorting needs.
  - `DndContext id="search-dnd"` gives stable `aria-describedby` ids for SSR. Transforms are written by hand with translate only (no `@dnd-kit/utilities`).
  - Announcements are rebuilt with `useMemo([index, chips])`. A ref-based version fails the React Compiler `react-hooks/refs` lint rule.
  - T2.4: `SearchResults` is mounted only when `request` is non-null, so idle shows the hero text. `useSearch` already had `skipToken` + `keepPreviousData` from T1.2. While refreshing, the list dims to 60% with `aria-busy`. The count goes in `aria-live="polite"`, and errors show inline with a Retry button.
  - A dev-only `console.debug("[search] request", params)` in `searchQuery`'s `queryFn` (behind `NODE_ENV === "development"`) is the request counter.
- **Files for next session:**
  - `lib/search/dnd.ts` (pure rules)
  - `components/search/SearchDnd.tsx` (context, sensors, `DragOverlay`; T8.2's chip-snap `dropAnimation` goes here)
  - `components/search/SearchBar.tsx`
  - `components/search/ChipTray.tsx` (`TrayChip`)
  - `components/search/SearchResults.tsx`: **interim rows** (title · artist, bpm, bars) that T3.2 replaces with `ResultList`/`ResultCard`. Status text, retry and dimming are already there; move them over.
- **Known bugs / gotchas:**
  - The Chrome MCP `left_click_drag` sends a single pointermove, which only *activates* the dnd-kit drag, so nothing drops. To test drags, dispatch a stepped PointerEvent sequence with JS. Real mouse drags aren't affected.
  - Tray chips don't set `touch-action: none` (so the tray still scrolls on touch), which means touch dragging from the tray is unreliable. Click-to-add works on touch.
  - First load shows plain "Searching…" text, not skeletons (T3.2). `?fixture=empty` shows "0 results" with no empty-state UI yet (T3.2).
  - Carried over: an "Open in editor" click within 300 ms of an edit can hand off the previous URL (T3.4).
- **Blocked:** nothing. PR #3 (Gate H4) still needs review/merge. Next is T3.1 (PreviewProvider).

### Session 4 (2026-11-14): T3.1 + T3.2
- **Done:** T3.1 PreviewProvider, T3.2 ResultCard + ResultList. lint/typecheck are clean and tests pass 58/58 (5 new in `lib/preview/loop.test.ts`, 6 in `lib/search/results.test.ts`). I checked these by hand in Chrome on fixtures, with no console errors or hydration warnings:
  - T3.1: a single `<audio>` element for every play. A cold start of `other.wav` reached the window start (5.333 s) about 1 ms after the click (local file). Switching cards on `mix.wav` jumps straight to the new window. The window loops at the end (10.52 → 0.07 on 0–10.667, 7.9 → 2.77 on 2.667–8.0, and the `ended` path on 5.333–16.0, which ends at the file end). Only one card shows Stop at a time. Stop pauses. Going to `/import` stops the preview (Activity hide).
  - T3.2: 8 fixture cards render. `?fixture=fallback` shows the banner, "—" for null BPM/key and a truncated long title. `?fixture=empty` shows "No matches, try fewer chips", and "Remove last chip (Melancholy)" removes it and updates the URL. Idle → typing shows 8 skeletons, then 8 cards. The status reads "N results[, expanded to Freesound][, updating…]".
- **Decisions:**
  - The player is a plain class (`lib/preview/player.ts`) with `subscribe`/`getSnapshot`. The snapshot is immutable `{item, status}` with status `idle | loading | playing | error`. `PreviewItem = {id, url, start, end}` uses **file time**, so the stems drawer (T5.2) passes `start_s - range_start_s` itself.
  - The window boundary is checked on rAF **and** on `timeupdate`, because background tabs get no rAF. The wrap happens one frame early (`LOOP_LOOKAHEAD_S = 1/60`). `ended` restarts the window when it ends at the file end.
  - `play()` sets `currentTime` before metadata loads (the browser's default playback start position), so there's no blip from 0. `play().then` sets "playing" because switching windows on an element that's already playing fires no `playing` event. An epoch counter ignores AbortErrors from superseded plays.
  - `warm(url)` sets `src` + `load()` only while nothing is active. Cards warm on pointerenter and focus.
  - `usePreviewStatus(id)` selects a primitive, so only the cards whose status changed re-render. `usePreviewSnapshot()` and `player.progress(id)` exist for the T3.3 playhead (poll `progress` from the waveform's rAF).
  - `useStopPreviewOnHide()` (a `useLayoutEffect` cleanup) is called in `SearchPage`.
  - `dispose()` doesn't clear listeners, because of StrictMode effect re-runs.
  - The card also shows the window as `m:ss.s–m:ss.s` and a "· Freesound" marker for `source === "freesound"`. Tags are muted text, not chip colors (tags aren't chip ids).
  - Retryable errors (`rate_limited`/`upstream_error`) toast with `id: "search-error"`, so repeats don't stack.
  - The empty-state subline says "Even Freesound came up empty" only when `fallback_used` is true.
  - Grid: 1 column, 2 at `xl`.
- **Files for next session:**
  - `components/search/ResultCard.tsx`:
    - T3.3: the waveform slot is the `h-12` placeholder div.
    - T4.1: the why note is a plain `line-clamp-2` `<p>`.
    - T3.4/T5.2: the Stems and Open in editor buttons go in the title row next to `PlayButton`.
    - T3.4: Space/Enter go on the `<AppCard>` (it already has `tabIndex=0` and `aria-labelledby`).
    - `previewItemOf(result)` is exported.
  - `components/search/ResultList.tsx`
  - `lib/search/results.ts`
  - `lib/preview/{player.ts,PreviewProvider.tsx,loop.ts}`
- **Known bugs / gotchas:**
  - The error UI (network banner, inline retry, toast) is unit-tested only through `searchErrorKind`/`searchErrorMessage`. There's no fixture that fails, so I didn't see it in the browser. Check it in T6.1 by stopping the API.
  - The Stems and Open in editor buttons aren't on the cards yet (T3.4, T5.2).
  - Time to sound was measured on local fixture WAVs only. Check real MP3 latency in T6.1.
  - Carried over: an "Open in editor" click within 300 ms of an edit can hand off the previous URL (T3.4).
- **Blocked:** nothing. PR #3 (Gate H4) still needs review/merge. Next is T3.3 (MiniWaveform).

### Session 5 (2026-11-14): T3.3 + T3.4 + Gate H8
- **Done:** T3.3 MiniWaveform, T3.4 editor hand-off + keyboard, and Gate H8 (PR #4 `feat(ws3): search flow`, https://github.com/codeArjya/Beatopia/pull/4). `origin/main` had nothing new (still cb05f68), so the rebase was a no-op. `make schema` + `make check-fixtures` passed (13 fixtures, 0 problems). lint/typecheck are clean, tests pass 72/72 (11 new in `lib/waveform/{peaks,limit}.test.ts`, 3 in `lib/links.test.ts`), and `pnpm build` passes. I walked through the gate in Chrome on fixtures (steps are in the PR body): stack Soul (drag) + Rhodes + Melancholy, see 8 waveforms, play with a moving playhead, Space/Enter on a focused card, Open in editor with the correct URL, and Back restores the search. No console errors.
- **Decisions:**
  - **PR #4 is stacked.** PR #3 (the shell) is still open from `ws3-web`, and `origin/ws3-web` is at session 1. So I pushed this session's work as `ws3-search-flow` and opened PR #4 with **base `ws3-web`**. That way #3 keeps reviewing only the shell. Merge #3, then retarget #4 to `main`. Local `ws3-web` now tracks `origin/ws3-search-flow`, so push with `git push origin ws3-web:ws3-search-flow` until #3 merges.
  - **Waveform:**
    - Decoding uses an `OfflineAudioContext(1, 1, 44100)`, so there's no autoplay warning and no gesture is needed.
    - Decoded buffers are kept in an LRU of **3** (a real track's `AudioBuffer` is around 60 MB). Only the peaks are cached long-term, via TanStack Query (`keys.peaks`, `staleTime: Infinity`, `gcTime` 30 min, `retry: false`).
    - At most 2 fetch+decode jobs run at once (`createLimiter`). Files over 30 MB (by Content-Length) are skipped.
    - Peaks are max-abs over all channels, stored raw. `normalizePeaks` scales them when drawing, with a 0.1 floor so near-silence isn't amplified into noise.
  - **Playhead:** a second canvas drawn in `text-primary` sits under a `clip-path: inset()` that a rAF loop updates from `player.progress(id)`, plus a separate 2 px line. The loop runs only while that card's status is playing/loading.
  - **Hand-off:**
    - `editorHref` rounds seconds to milliseconds and trims trailing zeros (`10.667`, `16`, `0`).
    - The card's "Open in editor" is a Next `<Link>` (`AppButton asChild`) that stops the preview on click. Below `sm` it shows only an icon.
    - Space/Enter toggle the preview only when the `<article>` itself has focus. Inner buttons and links keep their own keys, and `e.repeat` is ignored.
  - **Dropped the 300 ms debounce flush.** I tried a `flushUrl()` (replaceState before navigating, even with the push deferred a tick). Next still restores the history entry's own older URL on Back. The page kept by `<Activity>` rewrites the URL about 25 ms later anyway, so I removed the flush instead of keeping code that does nothing.
- **Files for next session:**
  - `components/search/ResultCard.tsx`:
    - T4.1: the why note is still the plain `line-clamp-2` `<p>`.
    - T5.2: the Stems button goes in the `flex shrink-0` action group next to "Open in editor" and `PlayButton`.
    - `editorHrefOf(result)` is exported.
  - `components/search/MiniWaveform.tsx`
  - `lib/waveform/{peaks,limit,decode,usePeaks}.ts`
  - `lib/links.ts`: the stems drawer's "Use in editor" (T5.2) should call `editorHref` with the stem name.
- **Known bugs / gotchas:**
  - The waveform's failure path (CORS or a bad file gives a flat line) is only checked by reading the code. No fixture has a broken URL. Check it in T6.1 against Supabase and Freesound preview URLs (this is the WS1 CORS need in §2).
  - Real windows fetch the track's whole audio file for the waveform, in addition to the `<audio>` preview. Check the bandwidth and the time to first waveform on real MP3s in T6.1. If it's too slow, the next step is server-side peaks, which is a contract proposal.
  - In fixture mode the editor placeholder always shows `track_detail.json` (Late Bloom), whatever `track=` says. That's expected.
  - If you click Open in editor within 300 ms of typing and the search page has been evicted or reloaded, Back loses that last edit (see Decisions).
  - Carried over: the error UI and real-MP3 latency are unchecked until T6.1. Touch drag from the tray is unreliable (click works).
- **Blocked:** nothing. PR #3 (shell) and PR #4 (search flow, stacked) need review. Merge #3 first. Next is T4.1 (why notes).
