# TestPilot — Design System

Single source of truth for the product's color language. Tokens live in
`web/src/index.css` as OKLCH CSS variables and are exposed to Tailwind via
`web/tailwind.config.js` (`brand-*`, `ink-*`). Changing a token here recolors
the whole app — never hardcode hex accents in components.

## Brand accent — Emerald

The product accent is **emerald `#10b981`** (`oklch(0.696 0.148 163)`), the same
green used on the login scene. It is applied **surgically**: primary actions,
links, selection, focus, active state, and success — never as a large-area
fill. Neutral surfaces and text stay as-is; the green is the one saturated note.

The `brand-*` ramp is not a plain lightness ladder — historically `600` is the
"primary solid" step (button / sidebar mark / progress) and `700` is the
"text-on-light + hover" step. The emerald ramp keeps those roles:

| Token | Role | Light | Dark |
|-------|------|-------|------|
| `brand-50` | subtle tint bg (badge, hover row) | `oklch(0.95 0.038 163)` | `oklch(0.33 0.05 163)` |
| `brand-100` | hover border | `oklch(0.88 0.07 163)` | `oklch(0.41 0.07 163)` |
| `brand-500` | bright dot / indicator | `oklch(0.70 0.15 163)` | `oklch(0.72 0.15 163)` |
| `brand-600` | **primary solid** (button, mark) | `oklch(0.64 0.16 163)` | `oklch(0.70 0.15 163)` |
| `brand-700` | link text + hover | `oklch(0.56 0.15 163)` | `oklch(0.80 0.13 163)` |
| `on-brand` | text/icon on `brand-600` | `oklch(0.99 0.01 163)` (white) | `oklch(0.18 0.03 163)` (ink) |

Contrast rationale: `brand-600` is kept a **bright** emerald in both themes so
the app's primary solid visually matches the login scene's signature
`#10b981` (they must read as the same green). White bold button text on the
light `brand-600` clears AA-large; dark ink text on the dark `brand-600` clears
AA. `brand-700` is darker than `600` in light (readable link text on white +
hover-darken) and lighter than `600` in dark (readable link text on the dark
surface). If small-text link contrast ever needs to be stricter, deepen
`brand-700` — not `brand-600` (which must stay matched to the login green).

## Preset accent themes (user-switchable)

The whole `brand-*` ramp is built from a single hue variable `--brand-h` (see
`index.css`). A preset theme therefore overrides **only the hue** and works in
both light and dark automatically:

```css
:root { --brand-h: 163; }        /* emerald default */
[data-accent="blue"]   { --brand-h: 250; }
[data-accent="violet"] { --brand-h: 292; }
[data-accent="amber"]  { --brand-h: 70; }
[data-accent="rose"]   { --brand-h: 18; }
```

Users pick a preset from the bottom-left account menu (sidebar). The choice is
persisted in `localStorage` (`tp_accent`) and applied on load by `lib/theme.ts`
`initTheme()` via a `data-accent` attribute on `<html>` — same pattern as the
light/dark mode (`tp_theme` / `data-theme`). To add a theme: append to `ACCENTS`
in `lib/theme.ts` and add one `[data-accent="…"]` hue line here. Emerald is the
default and the signature brand color.

## Neutrals & semantics (unchanged)

Neutral surfaces/text (`--surface`, `--panel`, `--line`, `--ink-*`) and semantic
status colors stay: success `--ok-*` (green, hue 150), danger `--bad-*` (red),
warning `--warn-*` (amber). Success stays hue-150 so it reads distinct from the
hue-163 brand emerald.

## Login scene

The login page (`pages/LoginPage.tsx`) is a bespoke dark scene: canvas `#050505`,
Cyber-Serif type (Newsreader / Space Grotesk / Noto Serif SC), an aidesigner
liquid-metal WebGL background, and the same emerald `#10b981` as its accent. It
intentionally overrides the app theme and does not consume `brand-*` tokens.
