# WS3 handoff: Web shell & search UX

**Owner P3 (laptop L3). Branch `ws3-web`.** For the human and the coding agent alike.

## 1. Mission
Build the app everyone sees first: the shell, the chip tray with drag-and-stack, the search bar, result cards with
instant preview, why notes, the stems drawer, desktop import, the typed API layer for every endpoint, and the visual
design (tokens from Claude Design).

**Done when:** a judge can stack `Soul` + `Keys` + `Melancholy`, hear a result's window within a second of clicking,
read its why note, open stems, and send it to the editor. It works on fixtures and in production.

## 2. Boundaries
- **Edit only:** `web/` except `web/app/editor/`, `web/components/editor/`, `web/lib/audio/`, `web/stores/` (WS4).
- **Provides:** app layout + providers + nav (WS4 mounts inside it), `lib/api` hooks for **every** endpoint
  (WS4 uses `useTrack`, `useStems`, `useJob`, `useAssist`), the `StemsDrawer` component (WS4 may embed it), the
  design tokens in `globals.css`.
- **Consumes:** `shared/fixtures` + generated `web/lib/types` until H12, then WS2's live API.
- **Editor hand-off URL (fixed):** `/editor?track={track_id}&start={start_s}&end={end_s}&stem={stem}`.

## 3. Kickoff prompt (paste into the agent)
```text
You are the coding agent for stream WS3 (Web shell & search UX). Read AGENTS.md, docs/CONTRACT.md and
docs/handoff/WS3-web-search.md fully. Only edit web/ outside the WS4 paths listed in AGENTS.md.
Do not write code yet. Create web/PLAN-ws3.md containing:
1. A final answer for every item in "Decisions" (§5): keep the recommended default unless you find a concrete
   reason not to. Check current APIs of the installed dnd-kit, TanStack Query, wavesurfer.js and shadcn versions.
2. "Needs from other streams" and "Contract changes" (each with the assumption you'll use meanwhile).
3. The task list from §6 refined into 1–2 hour checkbox tasks with acceptance checks, mapped to gates H4/H8/H16/H20.
4. A component tree for the search page.
Then stop and wait for review.
```

## 4. Human setup (once, ~5 min)
```bash
cd sample-app && cp /path/to/.env .env      # NEXT_PUBLIC_USE_FIXTURES=1 for now
cd web && pnpm install && pnpm dev           # http://localhost:3000
```
Separately (P3, while the agent builds the shell, ~30 min): in Claude Design, design the Search screen, Stems drawer and
Import state from the spec's "Look and design brief", and ask for **shadcn-compatible CSS variables** (background,
foreground, primary, muted, border, radius, plus `--chip-instrument|genre|mood|tempo|key`). Paste the tokens into
`docs/proposals/WS3-design-tokens.md` and tell the agent to apply them at H16.

## 5. Decisions (recommended defaults; the agent finalizes them in PLAN)
| Decision | Recommended default |
| --- | --- |
| Routing | `/` search (the home page), `/import` drop zone, `/editor` (WS4). Header: logo, search, Import button |
| Chip UX | Left tray grouped by category (from `/chips`); drag a chip into the search bar (dnd-kit), or click to add; stacked chips show as removable pills before the text; Backspace on empty text removes the last chip; search fires 300 ms after any change |
| Chip colors | One CSS variable per category (`--chip-*`); pills use a tint of their category |
| Result card | Mini waveform (static, drawn from the decoded window, cached), title + artist, BPM / key / bars in monospace, top 3 tags, license badge (tooltip = attribution), collapsible why note (fetch `/why` lazily when `why` is null), buttons: Play, Stems, Open in editor |
| Preview audio | One shared `HTMLAudioElement` for the whole page (only one preview at a time), seeks to `start_s` and stops at `end_s`, loops while held; Space toggles the focused card |
| Stems drawer | shadcn `Sheet` from the right; if `StemsResponse.stems` exists, show it right away, else poll `useJob` every 1 s with a progress bar; four rows with play/solo and "Use in editor" (opens the editor URL with `stem`) |
| Import | `/import`: drop zone (wav/mp3/flac/m4a/ogg, ≤ 25 MB) → `POST /imports` → poll the analyze job → show bpm/key/windows → "Open in editor" |
| State | TanStack Query for all server data (keys: `["search", req]`, `["track", id]`, `["job", id]`); local UI state in components; session id in localStorage |
| Empty / error states | Skeleton cards while loading; "No matches, try fewer chips" with a one-click "remove last chip"; a banner when `fallback_used` ("Expanded to Freesound") |
| Adapters layer | `components/adapters/` wraps shadcn primitives the app uses (`AppButton`, `AppCard`, `AppSheet`, `Pill`) so restyling happens in one place |
| Accessibility | Every chip and card is keyboard-reachable; drag has a click alternative |

## 6. Build tasks (in order)
1. **Shell** (H0–H2): layout, header, providers, `lib/api` hooks for every endpoint on top of the bootstrap client,
   session id, placeholder `/editor` link working. **Gate H4: merge the shell so WS4 can rebase.**
2. **Chip tray + search bar** (H2–H5): dnd-kit drag/stack/remove, debounced search via `useSearch`.
3. **Results** (H5–H8): result cards, shared preview player, open-in-editor link. **Gate H8: full search flow on fixtures.**
4. **Why notes** (H8–H9): lazy `/why`, collapse/expand, loading shimmer.
5. **Stems drawer** (H9–H12): both paths (ready vs job), progress, solo, "use in editor".
6. **Go live** (H12–H14): `NEXT_PUBLIC_USE_FIXTURES=0`, fix real-data issues (long titles, missing bpm, no results).
7. **Import flow** (H14–H16). **Gate H16: Tier 0 in production.**
8. **Design pass** (H16–H20): apply Claude Design tokens, typography (grotesk UI + monospace tabular numbers),
   motion (chip snap, result shuffle ≤ 200 ms), dark theme polish.
9. **Tier 2 (H20+):** `/events` calls (play/pick/skip), the "Expanded to Freesound" banner, a "Flip this sample" tips
   panel generated from the why note, keyboard shortcuts.
10. **Deploy web** (with WS2, H12–H14): Vercel project from `web/`, env vars set, production URL to the human.

## 7. Checks
`pnpm lint`, `pnpm tsc --noEmit`, `pnpm test` (Vitest for hooks/utilities), plus a manual run of the demo flow in Chrome
after each gate (the agent writes the steps it tested in its PR description).

## 8. Integration points
- H4: merge the shell first; WS4 builds the editor page inside your layout.
- `lib/api` is the only place that knows URLs; WS4 imports hooks from there. If WS4 needs a new hook, add it within a few hours.
- Chips come from `/chips` (generated from WS1's vocab); never hardcode chip lists.

## 9. Pitfalls
- Next.js App Router: anything using audio, dnd-kit or localStorage must be a client component (`"use client"`).
- Browsers block autoplay until a user gesture; first play must be from a click.
- Don't create a wavesurfer instance per card; draw static mini-waveforms on canvas.
- Seeking an MP3 is imprecise by a few ms; that's fine for previews (the editor decodes precisely).
- Keep the fixture mode working forever; it's the backup demo if Wi-Fi dies.

## 10. Cut list (first to go)
Tier 2 extras → motion → import page (keep the editor's own file drop if WS4 has one) → why-note lazy fetch (show only
cached notes) → drag-and-drop (keep click-to-add chips).

## 11. Later prompts
- `Switch to the live API (NEXT_PUBLIC_USE_FIXTURES=0) and fix every rendering issue with real data.`
- `Apply the design tokens in docs/proposals/WS3-design-tokens.md through the adapters layer; show before/after screenshots of / and the stems drawer.`
- `Demo hardening: make the search page work fully in fixture mode as an offline backup, toggled by ?offline=1.`
