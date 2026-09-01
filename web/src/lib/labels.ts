// Display labels for enum-valued fields. These are NOT i18n keys: the app's i18n
// scheme uses the English string as the key with only a zh bundle, so machine keys
// like "type.functional" render raw in EN. Keep these as explicit {zh,en} maps.

type L = Record<string, { zh: string; en: string }>;

export const CASE_TYPE_LABELS: L = {
  functional: { zh: "功能", en: "Functional" },
  smoke: { zh: "冒烟", en: "Smoke" },
  regression: { zh: "回归", en: "Regression" },
  acceptance: { zh: "验收", en: "Acceptance" },
  negative: { zh: "反向", en: "Negative" },
};

export const CASE_STATUS_LABELS: L = {
  draft: { zh: "草稿", en: "Draft" },
  active: { zh: "生效", en: "Active" },
  deprecated: { zh: "废弃", en: "Deprecated" },
};

export const CADENCE_LABELS: L = {
  none: { zh: "手动(不提醒)", en: "Manual (no reminders)" },
  daily: { zh: "每日", en: "Daily" },
  weekly: { zh: "每周", en: "Weekly" },
  biweekly: { zh: "每两周", en: "Biweekly" },
  monthly: { zh: "每月", en: "Monthly" },
};

/** Look up a label for the current language; falls back to the raw key. */
export function label(map: L, key: string, lang: string): string {
  const e = map[key];
  return e ? (lang.startsWith("zh") ? e.zh : e.en) : key;
}
