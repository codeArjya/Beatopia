# WS4 handoff: Editor & audio engine

**Owner P4 (laptop L4). Branch `ws4-editor`.** For the human and the coding agent alike.

## 1. Mission
Build the browser sampler: load a track window or stem, show it as a waveform with regions, and apply the op chain
(trim, slice, reverse, repitch, pitch shift, stretch, gain, fades, normalize, loop, filter, arrange) non-destructively
with undo. Then render it offline to a WAV, and host the chat panel that applies ops from `/assist`.

**Done when:** from an editor URL, a judge can chop a window into 4, reverse one slice, repitch −3, reorder the slices,
hear it, undo, and download a correct 44.1 kHz WAV. Chat-proposed ops appear in the same history.

## 2. Boundaries
- **Edit only:** `web/app/editor/`, `web/components/editor/`, `web/lib/audio/`, `web/stores/`.
- **Provides:** the `/editor` page, `lib/audio` (pure op engine + render + WAV), the editor store, `ChatPanel`.
- **Consumes:** WS3's layout and `lib/api` hooks (`useTrack`, `useStems`, `useJob`, `useAssist`); generated Op types
  in `web/lib/types`; fixture audio until H12; `/assist` from WS2 at ~H24.
- **Entry URL (fixed):** `/editor?track={track_id}&start={start_s}&end={end_s}&stem={stem}`; also accept a local
  file dropped onto the editor (decoded in-browser, no upload) as `track_id = "local"`.
- **Op semantics are fixed by CONTRACT §5** ("Op chain semantics"). Implement them exactly; WS2's `/assist` relies on them.

## 3. Kickoff prompt (paste into the agent)
```text
You are the coding agent for stream WS4 (Editor & audio engine). Read AGENTS.md, docs/CONTRACT.md (especially
"Op chain semantics") and docs/handoff/WS4-editor.md fully. Only edit web/app/editor/, web/components/editor/,
web/lib/audio/, web/stores/.
Do not write code yet. Create web/PLAN-ws4.md containing:
1. A final answer for every item in "Decisions" (§5): keep the recommended default unless you find a concrete
   reason not to. Check the current wavesurfer.js v7 Regions API and Tone.js offline rendering API in the
   installed packages.
2. "Needs from other streams" and "Contract changes" (each with the assumption you'll use meanwhile).
3. The task list from §6 refined into 1–2 hour checkbox tasks with acceptance checks, mapped to gates H8/H12/H16/H24.
4. The module design of lib/audio (types, functions, what is unit-tested).
Then stop and wait for review.
```

## 4. Human setup (once, ~5 min)
```bash
cd sample-app && cp /path/to/.env .env      # NEXT_PUBLIC_USE_FIXTURES=1 for now
cd web && pnpm install && pnpm dev
# open http://localhost:3000/editor?track=<id>&start=0&end=16&stem=mix
# (<id> = track.id in shared/fixtures/track_detail.json)
```
Until WS3's shell lands (H4), the agent builds inside the bootstrap placeholder page; after H4 it rebases.
Test in Chrome. You mostly just listen to the results and confirm exports open in a DAW or QuickTime.

## 5. Decisions (recommended defaults; the agent finalizes them in PLAN)
| Decision | Recommended default |
| --- | --- |
| Engine core | `lib/audio` works on a plain `PcmBuffer = { sampleRate: number; channels: Float32Array[] }`, not on `AudioBuffer`, so ops are pure functions and unit-testable in Vitest/Node. Convert at the edges only |
| Evaluation | `evaluate(sources, state) → Map<clipId, PcmBuffer>` replays the op list from the sources (CONTRACT semantics); memoize per op-prefix hash so adding one op only recomputes the affected clip |
| Ops needing Web Audio | `repitch`, `filter`, `stretch_to_bpm` via `OfflineAudioContext` (playbackRate, BiquadFilterNode); `pitch_shift` and `keep_pitch` stretch via `Tone.Offline` (PitchShift / GrainPlayer); others (trim, slice, reverse, gain, fades, normalize, loop) in pure TS |
| Slicing | `count` → equal parts snapped to the nearest beat (beat_times shifted into clip time) or transient (simple spectral-flux onset detector in `lib/audio/onsets.ts`); `at[]` explicit; children `c1.1…c1.n` |
| Undo / redo | Undo pops ops (a chat response counts as one group); redo stack cleared on any new op; history list shows each op in plain words ("Reverse slice 3") |
| Waveform | wavesurfer.js v7 on the *rendered* active clip (re-render on change); Regions plugin for selection; slice boundaries as region markers; Timeline plugin with bar ticks from bpm |
| Arrangement lane | Horizontal strip of slice tiles (dnd-kit sortable), duplicate with Alt-drag or a "+" button; produces an `arrange` op |
| Playback | `AudioContext` + `AudioBufferSourceNode` on the full render; loop toggle; playhead synced to wavesurfer; Space = play/stop |
| Controls | Toolbar: Trim to selection, Slice (2/4/8/16 + snap mode), Reverse, Repitch (−12…+12 semitone stepper), Pitch shift (advanced), Fit to BPM, Gain, Fade in/out, Normalize, Loop ×, High/Low-pass |
| Shortcuts | Space play, S slice selection at playhead, R reverse, ↑/↓ repitch ±1, ⌘Z / ⇧⌘Z undo/redo, E export |
| Export | 44.1 kHz 16-bit PCM WAV (`lib/audio/wav.ts`, about 40 lines), stereo if any source is stereo; filename `{title}-{bpm}bpm-{key}.wav` sanitized; also record a `export` event via `lib/api` |
| Stems in editor | A "Stems" button opens WS3's `StemsDrawer`; choosing a stem adds it as a new clip source |
| Chat panel | Right-side panel; sends `AssistRequest` (messages + current `EditorState`); shows the reply and a preview of the proposed ops with Apply / Discard; Apply appends them as one undo group |

## 6. Build tasks (in order)
1. **Engine skeleton + tests** (H0–H2): `PcmBuffer`, decode/encode helpers, trim, slice (none/beat), reverse, gain,
   fades, normalize, loop, render arrangement, WAV encoder. Vitest: lengths, sample-exact reverse, fade curves, WAV header.
2. **Store** (H2–H3): Zustand `editor` store holding the EditorState shape plus undo/redo stacks, selection, active clip, decoded sources.
3. **Editor page on fixtures** (H3–H6): load from URL params via `useTrack` (fixture), decode, waveform + regions,
   toolbar for trim/slice/reverse, playback.
4. **Export** (H6–H8). **Gate H8: chop → reverse → export works on fixture audio.**
5. **Web Audio ops** (H8–H11): repitch, filter, stretch_to_bpm, pitch_shift via Tone.Offline; transient snap.
6. **Arrangement lane + history panel + shortcuts** (H11–H14).
7. **Go live** (H14–H16): real tracks and stems from production; handle missing bpm (disable beat snap), long windows,
   CORS-safe decoding from Supabase public URLs. **Gate H16: Tier 0 in production.**
8. **Stems + local file drop** (H16–H19).
9. **Chat panel** (H19–H24): against the `assist.json` fixture first, then live `/assist`. **Gate H24.**
10. **Polish** (H24–H30): performance (render in chunks, memoization), visual pass with WS3's tokens, edge-case fixes.

## 7. Checks
`pnpm lint`, `pnpm tsc --noEmit`, `pnpm test` (the lib/audio suite must stay green), plus a manual "golden" check:
export the demo-script edit and confirm duration and pitch by ear (and duration in the file info).

## 8. Integration points
- H4: rebase on WS3's shell; mount the editor in its layout.
- Need a new API hook? Ask the human to have WS3 add it, or write a proposal. Don't call `fetch` directly.
- `EditorState` sent to `/assist` must validate against the generated schema; WS2 rejects anything else.

## 9. Pitfalls
- Create the `AudioContext` only after a user gesture (Chrome autoplay policy).
- `OfflineAudioContext` length must be computed up front; repitch changes length by 2^(−st/12).
- Tone.js uses its own context; for offline renders use `Tone.Offline` and convert the result into `PcmBuffer`.
- Reversing a clip with a fade: order matters (op order is the truth; don't "optimize" it).
- Decoding cross-origin audio needs CORS headers; Supabase public bucket URLs are fine, while arbitrary Freesound
  preview URLs may not be, so request them through WS2 if needed (raise it early).
- Large renders block the main thread; keep renders ≤ 60 s of audio and show a spinner.

## 10. Cut list (first to go)
Chat panel → pitch_shift / keep_pitch stretch → filter → transient snap (keep beat/none) → arrangement drag (keep
default order + duplicate button). Never cut: trim, slice, reverse, repitch, undo, export.

## 11. Later prompts
- `Add Vitest cases for every op in CONTRACT §5 that isn't covered yet, then fix any failures.`
- `Profile adding one op on a 16-bar clip; if render takes > 150 ms, add memoization per op prefix.`
- `Wire the chat panel to the live /assist and test these prompts: "chop into 4", "reverse the last slice", "make it 2 bars and loop it 4 times".`
