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
- [x] **T4.1 WhyNote** (1 h). `useWhy(windowId, { initialData: result.why, enabled })`. Collapsed to 2 lines and expandable. When `why` is null, the fetch happens on first expand **or** first play (no fetch-on-scroll, to save Gemini calls). Loading shimmer, inline retry on error.
  *Accept:* on fixtures, the 2 results with `why: null` show a shimmer and then the note. Cached notes show with no request.

### Stems drawer, H9 → H12
- [x] **T5.1 StemsDrawer data flow** (1.5 h). The `useStemsFlow(trackId, start, end)` hook handles both the ready path and the job path, returns `{status, progress, stems, error, retry}`, clamps to 60 s, and invalidates `["track", id]` when the job is done.
  *Accept:* in fixture mode, `jam_1532881` with 0–10.667 is ready at once, and a range past 16 s goes queued → running (2 polls) → done.
- [x] **T5.2 StemsDrawer UI** (1.5 h). Sheet, progress bar, one row per stem with Play (solo, offset-aware) and "Use in editor", `onPick` for WS4.
  *Accept:* unit test for the stem offset math. Manually: each stem plays its matching segment, and "Use in editor" opens `…&stem=drums`. Esc closes and returns focus to the Stems button.

### Go live + deploy, H12 → H14 (together with WS2)
- [x] **T6.1 Live API** (1.5 h). `NEXT_PUBLIC_USE_FIXTURES=0` and fix what real data breaks: long titles, missing bpm or key, no results, slow searches (> 3 s spinner text), CORS on the waveform fetch.
  *Accept:* 5 real queries render without layout breaks. Fixture mode still passes the H8 walkthrough.
  *Status (session 7):* hardening done and H8 re-passed. Later in the session the API came up, and 5 real queries rendered with no layout breaks (see the session 7 addendum).
- [x] **T6.2 Vercel deploy** (1 h). Project rooted at `web/`, env vars set, production URL sent to the human, CORS confirmed with WS2.
  *Accept:* the production URL runs a live search with no CORS errors in the console.

### Import, H14 → **Gate H16** (Tier 0 in production)
- [x] **T7.1 ImportDropzone** (1 h). Drag-and-drop or click-to-browse, the client-side checks (`lib/import/validate.ts`), and upload through `useImport`.
  *Accept:* unit tests for extension, size and MIME edge cases. A 30 MB file or a `.txt` is rejected before upload with a clear message.
- [x] **T7.2 Analyze polling + summary** (1 h). Progress, a summary of the `TrackDetail`, the `["track", id]` cache seeded, and "Open in editor" using the best window.
  *Accept:* fixture import → done → summary shows 90 BPM, A minor, and the editor opens. Live: upload a real 10 s WAV in production.
  *Status (session 8):* code done and the fixture path passes in Chrome. The live run first failed because no worker was running. After WS1 started the worker, a real 10 s WAV went upload → summary in 4.9 s against the production API (this branch on `localhost:3000`, live mode), and the editor opened. Ticked.
- [x] **Gate H16:** in production, stack Soul + Keys + Melancholy → hear it → read the why note → open stems → send to the editor, and import → editor.
  *Status (session 8):* **passed in production** after PR #7 merged (72773d0). Search → hear → why → stems → editor, and import → editor (6.1 s to the summary) all run on https://beatopia-liart.vercel.app. The editor at the end of both paths is still WS4's placeholder (WS4's work isn't on GitHub yet). The WS3 hand-off URLs are correct.

### Design pass, H16 → **Gate H20**
- [x] **T8.1 Apply the Claude Design tokens** (1.5 h) through `globals.css` and the adapters only.
  *Accept:* before and after screenshots of `/` and the stems drawer. No feature component edited for colors.
- [x] **T8.2 Typography + motion** (1.5 h). Grotesk UI (Geist) with monospace `tabular-nums` numbers, a chip snap animation (dnd-kit `dropAnimation`), and a result fade/shuffle of at most 200 ms in CSS only, with no new dependency. `prefers-reduced-motion` is respected.
  *Accept:* the animations don't delay audio start, and reduced motion turns them off.
- [x] **T8.3 Dark polish + a11y sweep** (1 h). Contrast of chip tints on dark, focus rings, keyboard-only run of the whole flow.
  *Accept:* the flow is doable without a mouse, and chip text contrast is ≥ 4.5:1.
- [ ] **Gate H20:** design pass merged, screenshots in the PR.
  *Status (session 9):* code + before/after screenshots in PR #17; tick on merge.

### Tier 2 (H20+, in cut-list order)
- [x] **T9.1 Events** (1 h). `usePostEvent` fire-and-forget for `play` (first play per card per query), `pick` (open in editor or use stem), and `skip` (another card played within 1.5 s of starting this one).
- [x] **T9.2 Offline backup** (1 h). `?offline=1` switches `lib/api` to fixtures at runtime and is kept in `sessionStorage`.
- [x] **T9.3 "Flip this sample" tips** (1.5 h), drawn from the why note.
- [x] **T9.4 Keyboard shortcuts** (1 h). `/` focuses search, `j`/`k` move between cards, `s` opens stems, `e` opens the editor, `?` shows help.

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

### Session 6 (2026-11-14): T4.1 + T5.1 + T5.2
- **Done:** T4.1 WhyNote, T5.1 `useStemsFlow`, T5.2 StemsDrawer UI. `git fetch && git rebase origin/main` was a no-op (`origin/main` is still cb05f68). Fixtures only; no env or deploy changes. lint/typecheck are clean and tests pass 87/87 (4 new in `lib/search/why.test.ts`, 11 in `lib/stems/flow.test.ts`). I checked these by hand in Chrome on fixtures, with no console errors:
  - T4.1: the 6 cached notes show with no fetch. "More" appears only when a note overflows 2 lines. The 2 `why: null` cards (Velvet Static, Dusty Rhodes) show a "Why this works as a sample" button. Clicking it shows the shimmer, then the note expanded with "Less". Playing the other card shows the shimmer, then the note collapsed.
  - T5.2: Stems on the first card (`jam_1532881`, 0–10.667) shows "Asking for stems…", then 4 rows (Drums, Bass, Vocals, Other). Drums plays solo (its button turns to Stop). Esc closes, stops the stem, and focus returns to the Stems button. "Use in editor" opens `/editor?track=jam_1532881&start=0&end=10.667&stem=drums`.
- **Decisions:**
  - **WhyNote:** "requested" is latched during render on the first expand or the first play/loading status of that card (`usePreviewStatus(window_id)`), never on scroll. `useWhy` gets `enabled: requested`, and the cached note seeds it, so cached notes never fetch. Overflow is measured with a ResizeObserver only while collapsed. The container is `aria-live="polite"`. An error shows "Couldn't load the note" with a Retry button (`refetch`).
  - **`useStemsFlow(trackId, start, end, enabled)`** lives in `lib/stems/useStemsFlow.ts`. The pure state machine is in `lib/stems/flow.ts` (`stemsFlowState` → `idle | requesting | queued | running | ready | error`, plus progress, stems and error). `queued` means a `job_id` came back but there's no poll yet. Ranges are clamped to 60 s (`clampStemsRange`). When the job finishes, `["track", id]` is invalidated. `retry` **resets** (not refetches) both the job query and the stems query, because a finished job has stopped polling and a re-request can return the same job id. `enabled` is the drawer's `open`, so a closed drawer sends nothing. Closing mid-job pauses polling (no observer), and reopening resumes it.
  - **Stem preview offset:** `stemPreviewItem(stem, start, end)` maps the window into file time (`start - range_start_s`), clamped to what the file covers. Stem preview ids start with `stem:`. Closing the drawer stops a `stem:` preview but leaves a card's mix preview playing.
  - **StemsDrawer API** (`components/stems/StemsDrawer.tsx`): `<StemsDrawer trackId startS endS open onOpenChange trackTitle? onPick? />`. `trackTitle` is new (sheet header). With `onPick`, "Use in editor" calls it and stops the preview. Without it, the button is a Link to `editorHref(... stem)` and closes the sheet. Stems are sorted drums, bass, vocals, piano, guitar, other, mix. The progress bar is indeterminate while requesting, then shows the job's `progress`.
  - **AppSheet focus return:** Radix only refocuses a `DialogTrigger`, and our sheets are controlled without one, so focus fell to `<body>`. `AppSheet` now records `document.activeElement` in `onOpenAutoFocus` and refocuses it in `onCloseAutoFocus`. WS4 gets this for free.
  - `PlayButton` moved out of `ResultCard.tsx` into `components/search/PlayButton.tsx` (new optional `className`), and both the card and the drawer rows use it.
  - The card's Stems button (icon only below `sm`) sits first in the action group, before "Open in editor" and Play. Each card holds its own closed `StemsDrawer`, which renders nothing until opened.
- **Files for next session:**
  - `components/search/WhyNote.tsx`, `lib/search/why.ts`
  - `lib/stems/{flow,useStemsFlow}.ts`
  - `components/stems/StemsDrawer.tsx` (tell WS4 about the props above, including `trackTitle`)
  - `components/adapters/AppSheet.tsx` (focus return)
  - `components/search/{ResultCard,PlayButton}.tsx`
- **Known bugs / gotchas:**
  - **The job path (queued → running → done) is only unit-tested** (`flow.test.ts`, through the fixture client: running, running, ready). Every fixture window is inside 0–16 s, so in the browser the drawer always takes the ready path. Check the progress bar and Retry against the live worker in T6.1.
  - The fixture client always returns `jam_1532881` stems whatever the track id, so every card's drawer shows the same 4 stems in fixture mode. That's expected.
  - The fixture `/why` reply is the same note for every window.
  - React synthetic events from the portaled drawer bubble to the card's `<article>` handlers (`onFocus` warms the card's audio, which does nothing while a preview is active). Space/Enter are safe because the card checks `e.target === e.currentTarget`.
  - Carried over: error UI, real-MP3 latency and waveform CORS are unchecked until T6.1. Touch drag from the tray is unreliable (click works).
- **Blocked:** nothing. PR #3 (shell) and PR #4 (search flow, stacked) still need review, and this session's commits are local on `ws3-web` (not pushed). Next are T6.1/T6.2 (live API and deploy), which need WS2's API URL and Vercel access (§2).

### Session 7 (2026-11-14): T6.1 (partial), T6.2 (blocked)
- **Done:** `git fetch && git rebase origin/main` brought in 0877d84 (WS1 CLAP + live seed, #5). Nothing changed under `docs/CONTRACT.md`, `api/app/models`, `shared/` or `web/lib/types`. `make schema` + `make check-fixtures` passed (13 fixtures, 0 problems). T6.1 hardening is in commit `fix(ws3): harden search for the live API`. lint/typecheck are clean, tests pass 94/94 (6 new in `lib/api/client.live.test.ts`, the rest in `results.test.ts`/`queries.test.ts`), and `pnpm build` passes. **Gate H8 re-passed in Chrome on fixtures:** Rhodes + Soul + Melancholy stacked, 8 waveforms, play with a moving playhead, Open in editor → `/editor?track=jam_1532881&start=0&end=10.667&stem=…`, Back restores the chips. The only console exceptions were the "message channel closed" error, which comes from a browser extension, not the app.
- **The live API (`https://45-77-216-35.sslip.io`) was unreachable all session.** From this laptop, ports 80, 443, 8000 and 22 all time out (DNS resolves to 45.77.216.35). From Chrome, `fetch(/health)` timed out after 15 s. So the VM is down or firewalled, not only CORS. **The T6.1 acceptance (5 real queries) has not been checked yet**, so the box stays unticked.
- **Checked live mode against the dead API** (dev server with `NEXT_PUBLIC_USE_FIXTURES=0 NEXT_PUBLIC_API_URL=… next dev -p 3001`, so `.env.local` stays on fixtures): after 3 s the status reads "Still searching… the first search can take a few seconds". At about 20 s it shows "The search took too long. Try again." with Retry, and the tray shows "Couldn't load chips." with Retry. This closes the carried-over "error UI unchecked" item for the timeout path.
- **Decisions:**
  - **Request timeout:** `request()` in `lib/api/client.ts` uses `AbortSignal.timeout`. `REQUEST_TIMEOUT_MS` = 20 s; `/imports` gets 120 s. A `TimeoutError` becomes `ApiError(0, "timeout")`, and any other fetch failure is still `network_error`. A CORS failure looks like `network_error` ("Failed to fetch").
  - **Retry policy:** `retryOnceUnlessTimeout` (`lib/api/queries.ts`) is the QueryClient default in `app/providers.tsx` and is also set on `searchQuery`. Before, the default was `retry: 1` with no timeout, so a dead API showed skeletons forever. After a timeout it now errors in about 20 s. Stems and events still use `retry: false`.
  - `searchErrorKind`: `timeout` is "retryable" (inline Retry + toast), with its own message.
  - **Slow text:** `SLOW_SEARCH_MS` = 3000. `useSlow(active, key, ms)` (`lib/search/useSlow.ts`) restarts its clock when the request key changes. The status reads "Still searching…" while pending, or "…, still updating…" on a refetch.
  - **Card actions use container queries:** the card is `@container`, and the "Stems" and "Open in editor" labels show only at `@lg` (card ≥ 32rem). In the `xl` two-column grid the cards are about 470 px, so they show icons only and the title gets the space ("Late Bloom (Instru…" before, full title now). Checked with an injected 80-char unbroken file name and a 45-char tag: both truncate with a `title` tooltip, and the page doesn't scroll sideways.
  - Long unbroken strings: tags are `max-w-48 truncate`, `WhyNote` is `break-words`, and the `AppSheet` title is `line-clamp-2 break-words`.
  - Missing bpm/key already show "—" through `MonoStat`; nothing changed.
- **T6.2 prep (nothing created):** the Vercel CLI is installed (64.5.0) but **logged out**, and there is no `.vercel/` link. **`web/` imports `../shared/fixtures`** (`@fixtures/*`, and `turbopack.root` is the repo root). So the Vercel project needs **Root Directory = `web`, deployed from the repo root** (Git integration, or `vercel` run at the repo root after linking). If you deploy from inside `web/` alone, the build breaks. Env vars to set: `NEXT_PUBLIC_USE_FIXTURES=0`, `NEXT_PUBLIC_API_URL=https://45-77-216-35.sslip.io`. Both are inlined at build time, so changing them needs a redeploy.
- **CORS note for WS2:** origins `http://localhost:3000` plus the production `https://<project>.vercel.app` (preview deploys would need `allow_origin_regex=r"https://<project>-.*\.vercel\.app"`). Methods GET, POST, OPTIONS. Header `Content-Type`: JSON POSTs are preflighted. No cookies, so no `allow_credentials`. Error responses (4xx/5xx, incl. 422 and unhandled 500s) must carry the CORS headers too, or the browser reports them as `network_error`. Audio hosts (Supabase Storage, Freesound previews) need `Access-Control-Allow-Origin` for the waveform `fetch()`; that's WS1/Storage, not the API.
- **Files for next session:** `lib/api/client.ts` (timeout), `lib/api/queries.ts` (`retryOnceUnlessTimeout`), `lib/search/{results,useSlow}.ts`, `components/search/{ResultList,ResultCard}.tsx`, `app/providers.tsx`.
- **Known bugs / gotchas:**
  - Next allows only **one `next dev` per directory**, so the fixture (:3000) and live (:3001) servers can't run at the same time. Stop one first.
  - With `useSlow`, if the key changes while a fetch is running, the clock restarts even though TanStack keeps the old request. That's harmless (the text just shows later).
  - Still unchecked against real data: real-MP3 waveform latency/bandwidth, waveform CORS on Supabase/Freesound URLs, the stems job path (progress + Retry) against the live worker, and `fallback_used` with real Freesound results. Carried over: touch drag from the tray is unreliable (click works).
- **Blocked:**
  - **T6.1 acceptance:** needs the API VM reachable (WS2/human: check the VM is running and that the Vultr firewall allows 443).
  - **T6.2:** needs the human to approve creating the Vercel project and setting the env vars, and to run `vercel login` (interactive).
  - Commits are local on `ws3-web` (not pushed). PR #3/#4 status was not checked this session.
- **Addendum (later in session 7): the live API came up.** The 5 real queries pass in Chrome (`dusty soul keys`, `punchy drums`, `melancholy piano`, `funky bass` + Melancholy chip, `zzqx nonsense`) on `next dev -p 3000` with `NEXT_PUBLIC_USE_FIXTURES=0`. Each returned 8 cards with real waveforms, no layout breaks and no console errors. A missing BPM ("The Notebook") shows "—". Playback and the playhead work. T6.1 ticked.
  - **Port matters:** the API's CORS allows only `http://localhost:3000`. On :3001 every call fails as `network_error`. The Vercel origin isn't allowed yet either (WS2 needs to add it for T6.2).
  - CORS is correct on preflight, GET, and 4xx error bodies. The Supabase audio sends `Access-Control-Allow-Origin: *`, so the waveform fetch works. Each file is a 180 s, 192 kbps MP3 (4,321,532 bytes); fetches take 0.2–0.6 s each.
  - Search latency (curl): 4.8–6.6 s for the first queries, then about 0.25 s. The "Still searching…" text is worth having.
  - **`/why` returns 502 `upstream_error`** ("notes are unavailable right now (auto-degraded after 3 failures)"). The note service is failing on WS2's side. The UI shows "Couldn't load the note." with Retry. Cached `why` notes from search do render.
  - Data notes for WS1/WS2: results often repeat one track (e.g. 3 of 8 cards are "A Sweaty Nightmare"); a nonsense query still returns 8 results (no empty state in practice); some BPMs are doubled (252 for a piano piece).
  - Still unchecked live: the stems job path (progress + Retry) and `fallback_used`.
- **Addendum 2 (T6.2 status):** the human made the Vercel project `beatopia` (team `arjyas-projects-caf2d320`): Root Directory `web`, Next.js preset, production URL **https://beatopia-liart.vercel.app**. Env: `NEXT_PUBLIC_API_URL` (Production only, encrypted) and `NEXT_PUBLIC_USE_FIXTURES` (Production + Preview, sensitive, so its value can't be read back). The API's CORS already allows the production origin and the preview `*.vercel.app` origins (preflight checked).
  - **Production still shows `main`'s bootstrap placeholder,** because the WS3 UI wasn't on `main`. With the human's OK, I force-pushed (with lease, pinned to `cc18bc3`; I checked nothing would be lost) local `ws3-web` to `ws3-search-flow` and retargeted **PR #4 to `main`**. It now has all 27 WS3 commits and **supersedes PR #3**: merge #4, close #3. Don't merge #3 first, because #4 is rebased and would conflict.
  - Push from now on with `git push origin ws3-web:ws3-search-flow`.
  - Left for T6.2 after the merge: confirm a live search on the production URL with no CORS errors in the console, then tick T6.2. `NEXT_PUBLIC_API_URL` isn't set for Preview, so preview builds fall back to `http://localhost:8000`. Add it if previews should hit the live API.
- **Addendum 3 (T6.2 done):** PR #4 was squash-merged (`32bc7f8`) and #3 closed. Production first came up **in fixture mode**: `NEXT_PUBLIC_USE_FIXTURES` was evidently `1`, and the variable is "sensitive", so its value can't be read back. With the human's OK I set `NEXT_PUBLIC_USE_FIXTURES=0` (Production + Preview) and added `NEXT_PUBLIC_API_URL=https://45-77-216-35.sslip.io/` for **Preview** (plain; it's the official API URL). Both went in through `vercel api /v9|v10/projects/beatopia/env`, with no local `.vercel` link. Then I ran `vercel redeploy … --target production`.
  - **Production check on https://beatopia-liart.vercel.app/?q=dusty+soul+keys:** `GET /chips` 200 and `POST /search` 200 against the live API; 8 real results with waveforms and the notes from search; playback with a moving playhead; **no console errors**. T6.2 ticked.
  - `NEXT_PUBLIC_*` values are inlined at build time, so any env change needs a redeploy.
  - **Git:** because #4 was squash-merged, local `ws3-web` was reset to `origin/main` (same files; I checked with `git diff`). Start new WS3 work from `main`. Rebasing the old per-commit history onto `main` conflicts.
  - Still open (WS2): `/why` 502 for notes that aren't cached.

### Session 8 (2026-11-14): T7.1, T7.2 (code), Gate H16 run
- **Done:** T7.1 ImportDropzone (ticked). T7.2's code is done and its fixture path passes, but it stays unticked because the live analysis can't finish (see Blocked). I also ran the Gate H16 flow in production and fixed the one WS3 failure it found. `origin/main` had nothing new (still 32bc7f8). lint/typecheck are clean, tests pass 108/108 (8 new in `lib/import/validate.test.ts`, 6 in `lib/import/flow.test.ts`), and `pnpm build` passes. Branch pushed as **`ws3-import`**; PR opened against `main`.
- **Checked by hand in Chrome:**
  - Fixtures, `/import`: `.txt`, a 30 MB `.wav`, and text renamed to `.mp3` are each rejected with a clear message and **no request**. A real WAV header goes uploading → queued → analyzing (2 polls) → summary (my_loop_01, 0:16.0, 90 BPM, A minor, 3 windows, `user-upload` + "Uploaded by you"). Open in editor → `/editor?track=imp_3f9a1c2e&start=0&end=10&stem=mix`, and the editor placeholder shows "my_loop_01", which proves the seeded `["track", id]` cache was used (the fixture track would be Late Bloom). No console errors.
  - **Production search (https://beatopia-liart.vercel.app):** Soul + Rhodes + Melancholy stacked through the tray filter (Enter), URL `?chips=genre.soul,inst.rhodes,mood.melancholy`. 8 live results with waveforms. Play → playhead moves. 5 of 8 notes came cached; "Why this works" on an uncached card fetched `/why` in ~2 s (**last session's 502 is fixed**). Stems on "Just the Two of Us" → 4 stems at once; Drums plays solo in ~300 ms; "Use in editor" → `/editor?track=jam_1544389&start=20.05&end=30.081&stem=drums`.
  - **Live import (this branch on `localhost:3000` in live mode, same API):** a generated 10 s WAV uploaded fine (`POST /imports` 200, ~1 s, CORS OK), then the analyze job stayed `queued` with progress 0 for 2+ minutes. 64 polls at 1 s each.
- **Gate H16 failures (cause → owner):**
  1. **The job worker isn't running.** Analyze job `2968f468-…` and a probe stems job `50bfe576-…` (`jam_1485349`, 20–30 s) both sit at `queued` / 0.0. The API itself is up (revision 56838ae). → WS1/WS2: start `worker` on the VM. This blocks import → editor, and stems for any track without pre-made stems (`jam_1485349`, `jam_1265033`, `jam_1026088`, `jam_1029230`, `jam_1432368`, and every `fs_*` fallback in my sample). The demo needs it.
  2. **The editor is still WS4's placeholder on `main`.** The hand-off URLs are right, but the page plays the full mix and ignores `stem`. → WS4 merge.
  3. **There's no "Keys" chip.** The live vocabulary has Piano, Rhodes, Wurlitzer, Organ, Clavinet, but no Keys. → WS1 (vocab) if the demo script must say "Keys"; otherwise say Rhodes.
  4. *(WS3, fixed)* With the worker down, the import page and the stems drawer spun on "Waiting…" forever. Both now say "may be busy or offline" after 30 s queued (`STUCK_QUEUE_MS`) and keep polling.
  5. *(Process)* Vercel **preview deployments are protected** (SSO "You need access"), so a branch can't be checked on its preview URL without a team owner granting access. I used `localhost:3000` in live mode instead. The import page goes into production only once the PR merges.
- **Decisions:**
  - Client checks mirror WS2's `app/core/imports.py` exactly: the extension list, **25 MiB** (`25*1024*1024`), non-empty, and the same 16-byte magic sniff (`sniffAudio`), including "named .mp3 but is really WAV". MIME is lenient (empty, octet-stream, `video/ogg`, `video/mp4` are fine), and only clearly non-audio types are rejected.
  - Import components live in `components/import/` (CONTRACT's tree says `components/search/`, but StemsDrawer already set the `components/<feature>/` precedent).
  - `importFlowState` (pure) maps upload + job → `idle | uploading | queued | analyzing | done | error` with `failedAt: upload | analyze`. Upload errors show in the drop zone with "Retry upload of X". Analysis errors show an alert with "Try again" (re-uploads the same file).
  - `useImportFlow` seeds `["track", id]` in an effect when done, and `reset` removes the old `["job", id]` (fixture mode reuses one job id).
  - `importEditorLink`: the window with the highest loopability (ties go to the earliest); with no windows, `0 → min(duration, 8 bars)`, or 16 s when there's no BPM.
  - The fixture analyze job now runs 2 "running" polls after each `createImport` (it's still "done" on the first poll if fetched without an import, so the old tests hold).
  - The summary has a PlayButton preview of the chosen window (id `import:…`) and the license + attribution (AGENTS.md rule).
  - The drop zone is a `<label>` around an sr-only file input (one tab stop, native picker). Window-level dragover/drop are blocked on `/import` so a near-miss drop doesn't navigate to the file.
- **Files for next session:** `lib/import/{validate,flow,useImportFlow}.ts`, `components/import/{ImportDropzone,ImportFlow,ImportSummary}.tsx`, `app/import/page.tsx`, `lib/api/client.ts` (fixture analyze polling), `components/stems/StemsDrawer.tsx` (stuck hint).
- **Known bugs / gotchas:**
  - The test imports from this session left 2 placeholder `imp_*` tracks and their queued analyze jobs in the production DB (plus 1 earlier one), and one queued stems job for `jam_1485349`. They'll run when the worker starts. That's harmless, but WS1 may want to delete them.
  - An import is lost if the tab reloads mid-analysis (job id only in memory). That's fine for the demo; a `?job=` URL param would fix it.
  - The hint text uses `text-amber-*` directly. Move it to a token in T8.1.
  - Next HMR resets the import page state when hooks change, so re-upload after edits.
- **Blocked:**
  - T7.2's live tick and Gate H16's import half: the worker (WS1/WS2).
  - Gate H16 "→ editor" is only as good as WS4's placeholder until WS4 merges.
  - Next: once the worker runs, re-run a live import in production after the PR merges, tick T7.2 and H16, then T8.1 (design tokens, if `docs/proposals/WS3-design-tokens.md` exists).
- **Addendum (2026-11-15): worker up, gate re-run.**
  - Rebased on `origin/main` (b7485cf, contract C7–C9: new `internal_error` code, CLAP/Gemini env). `make schema` made no changes; `make check-fixtures` passed 13/13. lint/typecheck are clean and tests pass 108/108. `internal_error` already falls through to the generic "Import failed: …" text.
  - The two jobs that were stuck yesterday are both `done`. The worker's analysis is accurate: the 90 BPM A-minor test file gave 90.67 BPM / A minor, one 0–10 s window, loopability 0.95.
  - **Live import through the UI:** `gate_h16_c_major_100.wav` went uploaded 0.6 s → 5% 1.7 s → 75% → 90% → summary 4.9 s, showing **99.4 BPM, C major** (generated at 100 BPM, C–E–G). The preview plays. Open in editor → `/editor?track=imp_9e766a4c&start=0&end=10&stem=mix`, and the placeholder shows the track. No console errors. T7.2 ticked.
  - **Stems job path (API):** `jam_1265033` 30–40 s went queued → running 0.15 → 0.65 → 0.8 → 0.875 → done in 13 s with 4 stems. The 30 s stuck hint won't fire at that speed.
  - **The editor is NOT merged:** `main` has only `web/app/editor/editor-placeholder.tsx`, and no WS4 PR exists (#1–#7). Failure 2 stands.
  - **Rebased branch not pushed:** the force-push to `ws3-import` (needed after the rebase) was blocked by the session's permission check. PR #7 still shows the pre-rebase commits. Run `git push --force-with-lease origin ws3-web:ws3-import`, or merge #7 as is (it doesn't conflict: b7485cf touches no `web/` files).
  - Gate H16 is still unticked. Left to do: merge #7 → re-run import on https://beatopia-liart.vercel.app/import → WS4 editor merge.
  - Test data in the production DB: imports `imp_22efb81b`, `imp_9e766a4c` (plus 2 earlier `gate_h16_test_loop` imports), and new range stems for `jam_1485349` (20–30 s) and `jam_1265033` (30–40 s). Harmless.
- **Addendum 2 (2026-11-15):**
  - The human disabled Vercel Authentication for previews (failure 5 resolved). https://beatopia-git-ws3-import-arjyas-projects-caf2d320.vercel.app returns 200 with no SSO redirect.
  - With the human's OK, I force-pushed the rebased branch to `ws3-import` (with lease). PR #7 is current.
  - **Import on the deployed preview** (live API): `gate_h16_preview.wav` uploaded 1 s → analyzing 2.2 s → summary 5.3 s, 99.4 BPM / C major. Open in editor → `/editor?track=imp_0e0bdaf7&start=0&end=10&stem=mix` shows the track. No console errors.
  - **WS4 editor:** no remote branch touches `web/app/editor`, `web/components/editor`, `web/lib/audio` or `web/stores` except `bootstrap` (the placeholder). The editor work exists only on the WS4 laptop and hasn't been pushed. Ask P4 to push their branch (expected `ws4-editor`) and open a PR.
- **Addendum 3 (2026-11-15): Gate H16 passed in production.** PR #7 was squash-merged (72773d0), and Vercel production built it. On https://beatopia-liart.vercel.app/import:
  - A `.txt` is rejected with no request.
  - `gate_h16_production.wav` (10 s) uploaded 0.8 s → analyzing 1.9 s → summary 6.1 s, showing 99.4 BPM / C major. The preview plays.
  - Open in editor → `/editor?track=imp_97a1001c&start=0&end=10&stem=mix` shows the track. No console errors.
  - Together with session 8's production search run, every H16 step passes. H16 is ticked.
  - Git: local `ws3-web` was reset to `origin/main` (same tree, checked with `git diff`). Start new WS3 work from `main`. The `ws3-import` branch is merged and can be deleted.
  - Open items outside WS3: the WS4 editor isn't pushed, and there's no "Keys" chip (WS1 vocab). Test imports `imp_97a1001c`, `imp_0e0bdaf7`, `imp_9e766a4c`, `imp_22efb81b` (+2 earlier) are in the production DB.
  - Next for WS3: T8.1 design tokens (needs `docs/proposals/WS3-design-tokens.md`).
- **Addendum 4 (2026-11-15): WS4 editor merged (#8, f5a94d8); integration check.** Rebased on `origin/main` (also 9eb65e5, contract C10: Freesound fallback rule + Freesound results first; no schema/fixture change). `make schema` made no diff; `make check-fixtures` passed 13/13. lint/typecheck are clean, **189/189** tests (WS4's included), and `pnpm build` passes (new `/editor/*-checks` routes). WS4 touched no WS3 paths.
  - **Production (https://beatopia-liart.vercel.app, f5a94d8), all passing:**
    - Search (Soul + Rhodes + Melancholy) → card Open in editor → the real editor decodes the window as clip c1 (10.031 s), with the waveform, bar timeline, chop/reverse/repitch tools and the assist panel. Only one `<main>` is visible (the search page is hidden by `<Activity>`). No horizontal scroll, no console errors.
    - Editor → Stems (our `StemsDrawer` through WS4's `onPick`) → "Use Drums in the editor" adds clip c2 with the "Undo removes this source" notice.
    - Import (10 s WAV) → summary → Open in editor → clip c1 10.000 s, 99.4 BPM / C major.
    - **The stems job path in the UI, live, for the first time:** editor Stems on that imported track went queued → 5% → … → 95% → 4 stems in 13 s.
  - Note: a card's hand-off carries the result's own `stem` (e.g. `stem=other` for a window on the "other" stem). That's intended: the card preview plays that same stem's `audio_url`.
  - **Fixed (WS3):** after "Use in editor" from the editor's Stems sheet, focus fell to `<body>`, because WS4 disables its Stems button while decoding and a disabled button can't take focus. `AppSheet`'s `restoreFocus` now waits for the opener to be enabled again (up to 15 s, and only if focus is still on `<body>`). Checked on localhost in live mode: focus was BODY during decode, then the Stems button.
  - For WS4 (no change needed): the editor page renders its own `<h1>Editor</h1>` and `<main>` in `max-w-5xl px-6`; the T8.1 design pass may want to line it up with the header's `max-w-7xl px-4 sm:px-6`.
  - More test data in production: `imp_b3022a69` and its range stems (0–10 s).

### Session 9 (2026-11-15): T8.1–T8.3, Gate H20 screenshots, T9.1–T9.4
- **Sync:** local `ws3-web` (42384e0) had the same tree as main's squash #10 (d34bd98), so nothing was lost. Work is on branch **`ws3-design`**, cut from `origin/main` b69c405 (WS1 #14/#15, WS2 #11/#16, WS4 #12). `make schema` gave no diff; `make check-fixtures` passed 13/13.
- **Done (all ticked):** T8.1 tokens, T8.2 type + motion, T8.3 dark polish + a11y, T9.1 events, T9.2 `?offline=1`, T9.3 flip tips, T9.4 shortcuts. lint and typecheck are clean, **261/261** tests pass (+39 new; WS4's failing test fixed, see below), and `pnpm build` passes.
- **Gate H20:** code and before/after screenshots (`web/docs/screenshots/{before,after}-{search,stems}.jpg`, live API, 1500 px wide) are in the PR. It stays unticked until the PR merges.
- **Checked by hand in Chrome** (localhost:3000, live API `https://45-77-216-35.sslip.io`):
  - The token look on `/`, the stems drawer, `/import` and the WS4 editor (which inherits the tokens). No console errors.
  - A keyboard-only run: Skip to search → chips stacked by filter + Enter → Tab to a card → Space plays → Tab → Enter opens stems (focus moves into the sheet) → Esc returns focus to the Stems button. The focus outline is purple and visible.
  - Events: play card 1 → `play`; play card 2 within 1.5 s → `skip`(1) + `play`(2); replay card 1 after 3 s sends nothing; Open in editor → `pick`. The live API answers **204**.
  - Offline: `?offline=1` shows the banner and fixture results, with no API requests. It survives a reload without the flag (sessionStorage). Go live → `?offline=0` brings back live results.
  - Shortcuts: `/` focuses search (and doesn't type the slash). `j`/`k` move between cards, `s` opens the stems sheet (and `j` is ignored while it's open), `e` opens the editor, and `?` opens the help, which returns focus to the card when closed.
- **Decisions:**
  - Tokens come from the human's pasted v2 sheet, recorded in `docs/proposals/WS3-design-tokens.md` (no contract change). Values live only in `app/globals.css`. Added `--skeleton` (shimmer on card, since `--muted` equals `--card`) and `--warning` (#E8C172, 11:1).
  - No new dependencies. The sheet's component map suggested React Aria, Framer Motion, vaul and cmdk; instead the `.chip` sticker is applied by the `Pill` adapter on the existing dnd-kit buttons, the shuffle is a CSS 180 ms rise-in, the stems drawer stays a right Radix sheet (handoff decision, and WS4 embeds it), fonts load through `next/font` (Figtree + Geist Mono), and there is no persistent player bar (`.player-bar` is kept for later).
  - The sticker tilt uses the CSS `rotate`/`scale` properties, not `transform`, so dnd-kit's inline sort transform still works. The tilt alternates with `:nth-of-type` in the bar.
  - `AppButton` skins each variant over shadcn (`cn` is tailwind-merge compatible). Primitives' `outline-none` needs an explicit `focus-visible:outline-solid`, or the outline never draws (this was a real bug; fixed everywhere).
  - Play is always the purple round button (the accent's main job). The waveform uses wave-played/unplayed with the glowing playhead.
  - `lib/design/contrast.test.ts` parses `globals.css` and checks every text/token pair for ≥ 4.5:1 and borders/ring for ≥ 3:1. Change a token and the test tells you.
  - Events: `lib/events/tracker.ts` is pure. `SearchEvents` (in `ResultList`) watches the shared preview player, so every way of playing counts. Stem/import previews are ignored. `StemsDrawer` gained an optional `onUse` (additive; WS4's `onPick` is unchanged).
  - Offline: `fixturesActive()` = build-time `USE_FIXTURES` || `isOffline()`, decided once per page load. `USE_FIXTURES` is still exported unchanged for WS4.
  - The idle page's "Open the editor on a fixture" link now shows only when fixtures are active (in live mode it went to "track not found").
  - Flip tips are client-side only: the note's advice sentences, then tempo (half/double-time or repitch BPM), relative key, chop, and stem ideas, at most 4. No new endpoint.
  - New a11y bits: a "Skip to search" link (the tray is ~150 tab stops), and an `AppDialog` adapter that returns focus to its opener.
- **Files that matter next:** `app/globals.css`, `components/adapters/{Pill,AppButton,AppInput,AppCard,AppSheet,AppDialog}.tsx`, `lib/design/contrast.ts`, `lib/events/{tracker.ts,SearchEvents.tsx}`, `lib/api/{offline.ts,useOffline.ts,client.ts}`, `components/shell/{SkipLink,StatusBanner}.tsx`, `lib/search/{flip,shortcuts}.ts`, `components/search/{FlipTips,SearchShortcuts}.tsx`.
- **Known bugs / notes:**
  - **WS4 test fixed (with the human's OK, test-only, WS4 path):** `lib/audio/cooperative.test.ts` "yields between sample chunks…" failed on `main`. `RenderWork` yields only after 8 ms of wall-clock work, and a fast machine normalizes 60 s of silence in under 8 ms, so it never yielded or aborted. The test now fakes `performance.now` (+10 ms per reading). It used to fail 5/5 alone; now it passes 5/5 alone and the full suite passes 261/261 three times in a row. `cooperative.ts` is unchanged. WS4 should know it was touched.
  - For WS4: in `components/editor/arrangement-lane.tsx` the `<ol>` uses `focus-visible:outline-2` after an inherited `outline-none`, so its focus outline needs `focus-visible:outline-solid` to show. (I briefly changed it by accident with a repo-wide sed and reverted it. WS4 paths are untouched.)
  - For WS4 (suggestion only): `components/editor/waveform.tsx` hardcodes `#64748b/#2563eb/#e11d48`. The tokens want `#4A4A57/#EDEDED/#8B5CF6`, cursorWidth 2, bars 2/2/2. `chat-panel.tsx` labels by `USE_FIXTURES`; use `fixturesActive()` so `?offline=1` reads right.
  - Grid rows stretch to the tallest card, so an expanded "Flip this sample" leaves empty space in its row neighbour. That's cosmetic.
  - The API's CORS allows only `http://localhost:3000` (plus production), so a dev server on another port shows "Couldn't load chips".
- **Blocked:** nothing. Merging the PR ticks Gate H20.

### Session 10 (2026-11-15): production shipped the design pass with the old stylesheet
- **Found while recording the demo video:** after PR #17 merged (43d98b8), https://beatopia-liart.vercel.app served the new markup with an **old compile of `app/globals.css`**: `@layer components;` was empty (no `.chip`, `.play-button`, `.eyebrow`, `.readout`, `.skeleton`, `.player-bar`), none of the design tokens (`--chip-idle-bg`, `--primary-hover`, …) were there, and `font-sans` still pointed at Geist. Chips rendered as bare text and the playing-state play button was invisible.
- **Cause (evidence, not a proven Turbopack root cause):** the source is right. A clean local `pnpm build` of 43d98b8 emits the correct 74.9 KB stylesheet. On Vercel, the production build and two earlier `ws3-design` previews (313745a, 6bb8ed2) all emitted the **same stale chunk** (`1q9fh9easdcla.css`, 73.5 KB) after "Restored build cache from previous deployment"; the last `ws3-design` preview (8496e02, same tree as `main`) emitted the correct one. I could not reproduce the stale output locally by building b69c405 and then 43d98b8 over the kept `.next/cache`.
- **Fix:** `experimental.turbopackFileSystemCacheForBuild: false` in `next.config.ts`, so `next build` never reads or writes `.next/cache/turbopack`. Cold compile is ~2 s locally, ~20 s for the whole Vercel build. Checks: lint and typecheck clean, 261/261 tests, `pnpm build` emits the correct CSS and no Turbopack cache directory.
- **After merging:** confirm production's stylesheet contains `.chip{` (`curl` the CSS linked from `/`). If it's ever stale again, redeploy in Vercel with "Use existing Build Cache" unticked.
