import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TestCase } from "../lib/api";
import { Checkbox, Input, Select } from "./ui";

const PRIOS = ["P0", "P1", "P2", "P3"];

// MeterSphere-style case picker: cases grouped by module with tri-state "select whole
// module" checkboxes, plus keyword + priority filters. Selection is a flat case_ids list
// (a static snapshot) — the caller owns it.
export function CasePicker({
  cases,
  selected,
  onChange,
}: {
  cases: TestCase[];
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [prio, setPrio] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const sel = useMemo(() => new Set(selected), [selected]);
  const ungrouped = t("Ungrouped");

  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return cases.filter(
      (c) =>
        (!prio || c.priority === prio) &&
        (!kw || `${c.case_key ?? ""} ${c.name} ${c.module ?? ""}`.toLowerCase().includes(kw)),
    );
  }, [cases, q, prio]);

  const groups = useMemo(() => {
    const m = new Map<string, TestCase[]>();
    for (const c of filtered) {
      const k = c.module || ungrouped;
      const arr = m.get(k);
      if (arr) arr.push(c);
      else m.set(k, [c]);
    }
    return [...m.entries()];
  }, [filtered, ungrouped]);

  const emit = (next: Set<number>) => onChange([...next]);
  const toggleCase = (id: number) => {
    const n = new Set(sel);
    n.has(id) ? n.delete(id) : n.add(id);
    emit(n);
  };
  const toggleModule = (rows: TestCase[]) => {
    const n = new Set(sel);
    const all = rows.every((c) => n.has(c.id));
    for (const c of rows) all ? n.delete(c.id) : n.add(c.id);
    emit(n);
  };
  const toggleCollapse = (k: string) =>
    setCollapsed((s) => {
      const n = new Set(s);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });
  const bulk = (add: boolean) => {
    const n = new Set(sel);
    for (const c of filtered) (add ? n.add(c.id) : n.delete(c.id));
    emit(n);
  };

  const modCount = new Set(cases.filter((c) => sel.has(c.id)).map((c) => c.module || ungrouped)).size;

  return (
    <div className="rounded-lg border border-[var(--line)]">
      <div className="flex items-center gap-2 border-b border-[var(--line)] p-2">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("Search cases")}
          className="h-8 flex-1"
        />
        <Select value={prio} onValueChange={setPrio} className="h-8 w-32">
          <option value="">{t("All priorities")}</option>
          {PRIOS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </Select>
      </div>
      <div className="flex items-center justify-between px-3 py-1.5 text-xs text-ink-500">
        <span>{t("{{n}} selected · {{m}} modules", { n: selected.length, m: modCount })}</span>
        <span className="flex gap-3">
          <button type="button" className="text-brand-700 hover:underline" onClick={() => bulk(true)}>
            {t("Select all")}
          </button>
          <button type="button" className="text-ink-500 hover:underline" onClick={() => bulk(false)}>
            {t("Clear")}
          </button>
        </span>
      </div>
      <div className="max-h-72 overflow-y-auto p-1">
        {groups.map(([mod, rows]) => {
          const selN = rows.filter((c) => sel.has(c.id)).length;
          const open = !collapsed.has(mod);
          return (
            <div key={mod}>
              <div className="flex items-center gap-1.5 rounded px-1 py-1 hover:bg-brand-50/40">
                <button type="button" onClick={() => toggleCollapse(mod)} className="text-ink-400">
                  {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </button>
                <Checkbox
                  checked={rows.length > 0 && selN === rows.length}
                  indeterminate={selN > 0 && selN < rows.length}
                  onChange={() => toggleModule(rows)}
                />
                <span className="text-sm font-medium text-ink-800">{mod}</span>
                <span className="text-xs text-ink-400">
                  {selN}/{rows.length}
                </span>
              </div>
              {open &&
                rows.map((c) => (
                  <label
                    key={c.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 pl-8 text-sm hover:bg-brand-50/60"
                  >
                    <Checkbox checked={sel.has(c.id)} onChange={() => toggleCase(c.id)} />
                    <span className="font-mono text-xs text-ink-400">{c.case_key ?? `#${c.id}`}</span>
                    <span className="truncate text-ink-800">{c.name}</span>
                    {c.priority && <span className="ml-auto text-[11px] text-ink-400">{c.priority}</span>}
                  </label>
                ))}
            </div>
          );
        })}
        {groups.length === 0 && (
          <div className="px-2 py-6 text-center text-xs text-ink-400">{t("No cases match.")}</div>
        )}
      </div>
    </div>
  );
}
