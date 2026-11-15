# WS3 design tokens (Beatopia v2, "late-night listening room")

Source: the Claude Design token sheet the human pasted into the WS3 session (2026-11-15).
**Applied in:** `web/app/globals.css` (the single source of truth for values) and `web/components/adapters/`.
This file records the decisions; it changes no contract (no types, endpoints or shared files).

## Look
Dark only (same values on `:root` and `.dark`). Simple like a streaming app: sticker chips, quiet lists, one
accent. Purple (`--primary #8B5CF6`) is rare: play buttons, the playhead, focus rings, the one main action per screen.
Text on purple is dark (`--primary-foreground #0D0D0F`, 4.6:1); white on purple fails (4.2:1).

## Tokens (summary; exact values in globals.css)
| Group | Tokens |
| --- | --- |
| Surfaces | `--background #0D0D0F`, `--card #151519`, `--secondary #1E1E24`, `--accent #2A2A32` (hover, not brand), `--popover #1E1E24` |
| Text | `--foreground #EDEDED` (16.6:1), `--text-secondary #A6A6B4` (8.1:1), `--text-tertiary #8A8A9A` (5.7:1) |
| Brand | `--primary #8B5CF6`, `--primary-hover #9D74F8`, `--primary-strong #A78BFA` (purple text, 7.1:1) |
| Lines | `--border #26262E` (decoration), `--input #6C6C85` (controls that must be seen, 3.6:1 on card) |
| Chips | `--chip-instrument #5FB3A8`, `--chip-genre #6FA0E6`, `--chip-mood #E083AE`, `--chip-tempo #B9CC6E`, `--chip-key #C8CCD8`; idle = plain gray label, picked = solid hue sticker with dark text, tilt and hard shadow |
| Audio | `--wave-played #EDEDED`, `--wave-unplayed #4A4A57`, `--playhead #8B5CF6` (+ the only glow), `--readout #EDEDED` |
| Shape | `--radius 12px`, `--radius-art 8px`, `--radius-pill 9999px`, chip radius 6px |
| Type | Figtree (UI, 400/500/600/800) + Geist Mono (numbers, `tabular-nums`) via `next/font` |
| Motion | nothing over 200 ms; chip snap 120 ms with a small overshoot; result shuffle 180 ms; all off under `prefers-reduced-motion` |

## Deviations from the sheet's component map (no new dependencies)
AGENTS.md forbids swapping libraries without a proposal, and T8.2 says "no new dependency". So:
- **Chips:** the `.chip` sticker look is applied by the `Pill` adapter on the existing dnd-kit + `<button aria-pressed>`
  chips, not React Aria `ToggleButton`/`TagGroup`. Keyboard and `aria-pressed` behave the same.
- **Results re-sort:** a CSS fade/rise of ≤ 180 ms, not Framer Motion `layout`.
- **Stems drawer:** stays the Radix `Sheet` from the right (handoff §5 decision; WS4 embeds it in the editor), styled
  with the sheet radius and popover surface, not a vaul bottom drawer.
- **Fonts:** loaded with `next/font/google` (self-hosted, no layout shift), not a CSS `@import url(...)`.
- **Player bar:** not built; previews play inline on each card. The `.player-bar` utility is kept for later use.

## For WS4 (their paths; suggestion only)
`components/editor/waveform.tsx` hardcodes `waveColor #64748b / progressColor #2563eb / cursorColor #e11d48`.
The sheet's values are `waveColor #4A4A57, progressColor #EDEDED, cursorColor #8B5CF6, cursorWidth 2, barWidth 2,
barGap 2, barRadius 2`.
