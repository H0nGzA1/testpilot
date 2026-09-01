import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { Project } from "../lib/api";

const SECTIONS: [string, string][] = [
  ["overview", "Overview"],
  ["cases", "Test Cases"],
  ["runs", "Runs"],
  ["compare", "Compare"],
  ["issues", "Issues"],
  ["settings", "Settings"],
];

export function CommandPalette({
  open,
  onClose,
  projects,
  pid,
}: {
  open: boolean;
  onClose: () => void;
  projects: Project[];
  pid: number | null;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [q, setQ] = useState("");

  useEffect(() => {
    if (open) setQ("");
  }, [open]);

  const items = useMemo(() => {
    const list: { label: string; hint: string; to: string }[] = [
      { label: t("Home"), hint: t("all projects"), to: "/" },
    ];
    for (const p of projects) list.push({ label: p.name, hint: t("project"), to: `/projects/${p.id}/overview` });
    if (pid != null) {
      for (const [key, label] of SECTIONS)
        list.push({ label: t(label), hint: t("section"), to: `/projects/${pid}/${key}` });
    }
    return list;
  }, [projects, pid]);

  const results = useMemo(
    () => items.filter((i) => `${i.label} ${i.hint}`.toLowerCase().includes(q.toLowerCase())),
    [items, q],
  );

  if (!open) return null;

  const go = (to: string) => {
    navigate(to);
    onClose();
  };

  return (
    <div className="tp-overlay fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-[12vh]" onClick={onClose}>
      <div
        className="tp-pop w-full max-w-lg overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-2.5">
          <Search className="h-4 w-4 text-ink-500" />
          {/* eslint-disable-next-line jsx-a11y/no-autofocus */}
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && results[0]) go(results[0].to);
              if (e.key === "Escape") onClose();
            }}
            placeholder={t("Jump to a project or section…")}
            className="flex-1 bg-transparent text-sm text-ink-900 outline-none placeholder:text-ink-500"
          />
          <span className="rounded border border-[var(--line)] px-1 text-[11px] text-ink-500">esc</span>
        </div>
        <div className="max-h-80 overflow-auto p-1">
          {results.length === 0 && <div className="px-3 py-6 text-center text-sm text-ink-500">{t("No matches")}</div>}
          {results.map((r, i) => (
            <button
              key={r.to}
              onClick={() => go(r.to)}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-ink-700 hover:bg-brand-50 hover:text-brand-700"
            >
              <span className="capitalize text-ink-900">{r.label}</span>
              <span className="text-xs text-ink-500">{r.hint}</span>
              {i === 0 && <CornerDownLeft className="ml-auto h-3.5 w-3.5 text-ink-500" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
