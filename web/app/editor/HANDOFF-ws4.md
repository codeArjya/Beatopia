# WS4 native/Tone DSP session handoff

Work from the Beatopia repo root on `ws4-editor`. Read root/web AGENTS.md, docs/CONTRACT.md, docs/handoff/WS4-editor.md, reviewed web/PLAN-ws4.md and this file. Use pnpm.cmd from web. Preserve WS4 ownership and generated wire types. The reviewed plan authorizes its own log updates. No dependencies, lockfile, generated types, API client, shared files or WS3 shell changes.

Started clean at `32af353`. Engine commit: `6e34953`; see git log for the UI/verification handoff commit. Only assigned H8-H12 audio work was implemented; no arrangement/history UI, shortcuts, production loader, stems, local import or chat work.

## Implemented

- `offline.ts` validates generated Op variants and plans rate/exact frames before allocation. Repitch rate = 2 ** (semitones / 12), fit ratio = target/original track BPM. Missing BPM rejects fit; output capped at 60 seconds.
- `native-offline.ts`: OfflineAudioContext source-rate rendering and BiquadFilterNode low/high-pass, with graph cleanup.
- `tone-offline.ts` + `serial.ts`: serialized Tone.Offline/GrainPlayer, explicit offline context, detune cents/rate, copying and disposal, global context restoration even on failure. Grains: 200 ms or clip duration/4 for short clips; overlap half a grain. Half-sample render-duration guard prevents Tone truncating e.g. requested 15 frames to 14; allocated output and scheduled stop remain exact.
- `onsets.ts`: 512-frame Hann FFT / 256-frame hop, positive spectral flux, median threshold, 40 ms suppression. RMS stereo analysis avoids phase cancellation. Snap detects on current PCM; rejects absent/collapsed cuts.
- Replay preflights repeated arrangement output before DSP, validates returned shape, maps beat frames and tracks display `tempoBpm` separately from original `bpm`. Original source BPM remains the fit reference per reviewed plan, including repeated fits.
- Store injects browser rendering; atomic failure, undo/redo and stale publication protection remain. Toolbar adds assigned pitch/tempo/filter controls and transient mode; fit disabled/explained without BPM.
- `/editor/audio-checks` is a development + fixtures-only verification page, outside the product flow. It measures actual native/Tone DSP and runs the fixture golden through decode/store/WAV. Browser APIs are not required by the Node engine tests.

## Passing checks

From web:

- `pnpm.cmd test lib/audio stores`: 13 files / 52 tests.
- `pnpm.cmd lint`.
- `pnpm.cmd tsc --noEmit`.
- `pnpm.cmd test`: 14 files / 59 tests.
- `git diff --check`.

Installed signatures rechecked: wavesurfer.js 7.12.12 Regions addRegion/drag cleanup/created/updated; Tone 15.1.22 Offline callback/channels/sampleRate, GrainPlayer AudioBuffer url/rate/detune/grains, output get/disposal. Installed Next client/page guides read.

Chrome 157 actual two-second 440 Hz stereo results:

| Check | Result |
| --- | --- |
| Native -3 repitch | rate 0.8408964152537145; 104888 frames; 370 Hz |
| 90->120, keep_pitch=false | 66150 frames (0.75x); 587 Hz |
| 90->120, keep_pitch=true | 66150 frames (0.75x); 440 Hz |
| Tone +3 / -3 | each 88200 frames; 525 / 370 Hz peaks; stereo |
| Low-pass at 1000 Hz | 100 Hz pass +0.05 dB; 5000 Hz stop -28.50 dB |
| High-pass at 1000 Hz | 5000 Hz pass +0.18 dB; 100 Hz stop -39.98 dB |
| Short Tone mono | 1, 15, 220, 4410 frames exact, finite |
| Fixture mix transient cuts | repeat at 176446, 352899, 529202 frames |

80 ms grains originally gave 437 Hz in the keep-pitch test; 200 ms fixed that measured case. Granular sidebands/musical quality still need listening. Queue tests prove ordering/release after failure; concurrent real Chrome pitch requests also pass. The final harness run after restart reports ALL AUTOMATED BROWSER CHECKS PASSED.

H8 golden passes in Node and Chrome: real fixture -> four equal chops -> reverse c1.4 -> undo/redo -> every sample -> WAV encode/decode. Actual editor UI completed those edits and downloaded:

`C:\Users\ethan\Downloads\Late Bloom (Instrumental)-90bpm-A minor.wav`

Independent full file read: WAVE PCM 1, 44100 Hz, 16-bit, stereo, 705600 frames, 16 seconds, 2822444 bytes. **The human confirmed the downloaded file opens and sounds correct.** Browser Play advanced with Loop checked; repitch during playback stopped/reset transport and updated duration. The 0..16 entry intentionally skips telemetry (no matching fixture window); 0..10 has a matching opaque window.

## Unmet/unrun acceptance

Earlier H4-H6, H6-H7 and H8 gaps were identified before building. H8 golden/download/file listening now pass, but overall H8 remains open because earlier prerequisite rows remain open. Remaining browser matrix:

- Invalid/missing parameters, nonzero window 5..15, Regions drag/clip-relative trim, decode failure/retry.
- Selection seek, cursor following, loop boundary, repeated navigation/unmount and node/listener cleanup instrumentation.
- Missing-BPM disabled fit on a browser unknown-BPM case (code disables it; renderer rejection tested).
- New pitch-shift/keep-pitch musical quality and transient usefulness by ear. Human confirmation above applies to the H8 golden only.

H8-H10 and H10-H12 boxes remain unchecked despite implementation and automated Chrome measurements passing. No bootstrap checks blocked. No silent feature cut. If gate work slips: chat -> advanced pitch/keep-pitch -> filter -> transient snap -> arrangement drag. Retain trim/slice/reverse/repitch/undo/export.

Environment: OneDrive/node_modules churn triggered a Turbopack `os error 32` dependency read failure during a later pitch-shift toolbar attempt. Restart restored compilation; all automated Chrome checks passed afterward. That later toolbar attempt itself is not counted as passed. Google Fonts used fallback fonts; Grammarly injected hydration attributes. No WS3/dependency/OS-setting workaround. Dev server stopped at handoff. Git index writes need sandbox escalation because repo-root `.git` lies outside writable web.

## Fresh session

1. Inspect status/branch/recent commits and read the files above; preserve existing work.
2. From web PowerShell: `$env:NEXT_PUBLIC_USE_FIXTURES='1'; pnpm.cmd dev`.
3. Open `http://localhost:3000/editor/audio-checks`, press Run audio checks; expect ALL AUTOMATED BROWSER CHECKS PASSED.
4. Finish the remaining acceptance matrix in `http://localhost:3000/editor?track=jam_1532881&start=0&end=16&stem=mix`. Confirm new DSP by ear. Mark each plan box only when every criterion passes; record blocked/unrun checks separately.
5. Take only the next human-assigned session. Do not automatically start H12-H16 arrangement/production work.
