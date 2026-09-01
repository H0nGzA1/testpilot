export type ThemeMode = "system" | "light" | "dark";

const KEY = "tp_theme";

export function getTheme(): ThemeMode {
  return (localStorage.getItem(KEY) as ThemeMode) ?? "system";
}

export function setTheme(mode: ThemeMode): void {
  localStorage.setItem(KEY, mode);
  applyMode(mode);
}

function applyMode(mode: ThemeMode): void {
  const root = document.documentElement;
  if (mode === "system") delete root.dataset.theme;
  else root.dataset.theme = mode;
}

/* ---- accent (preset color theme) — overrides only the brand hue, see index.css ---- */
export type Accent = "emerald" | "blue" | "violet" | "amber" | "rose";

export const ACCENTS: { k: Accent; hue: number; zh: string; en: string }[] = [
  { k: "emerald", hue: 163, zh: "翡翠", en: "Emerald" },
  { k: "blue", hue: 250, zh: "海蓝", en: "Blue" },
  { k: "violet", hue: 292, zh: "靛紫", en: "Violet" },
  { k: "amber", hue: 70, zh: "琥珀", en: "Amber" },
  { k: "rose", hue: 18, zh: "玫瑰", en: "Rose" },
];

const ACCENT_KEY = "tp_accent";
const DEFAULT_ACCENT: Accent = "emerald";

export function getAccent(): Accent {
  const v = localStorage.getItem(ACCENT_KEY) as Accent | null;
  return v && ACCENTS.some((a) => a.k === v) ? v : DEFAULT_ACCENT;
}

export function setAccent(accent: Accent): void {
  localStorage.setItem(ACCENT_KEY, accent);
  applyAccent(accent);
}

function applyAccent(accent: Accent): void {
  document.documentElement.dataset.accent = accent;
}

/** Swatch color for a hue, matching the light-theme brand-600 solid. */
export function accentSwatch(hue: number): string {
  return `oklch(0.64 0.16 ${hue})`;
}

export function initTheme(): void {
  applyMode(getTheme());
  applyAccent(getAccent());
}
