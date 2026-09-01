import clsx from "clsx";
import { ChevronDown, ChevronsUpDown, ChevronUp } from "lucide-react";
import { useMemo, useState } from "react";

type Dir = "asc" | "desc";

// client-side sort + pagination for the small tables in this app.
export function usePagedSort<T>(
  rows: T[],
  accessors: Record<string, (row: T) => string | number | null | undefined>,
  opts?: { initialKey?: string; initialDir?: Dir; pageSize?: number },
) {
  const pageSize = opts?.pageSize ?? 25;
  const [sortKey, setSortKey] = useState(opts?.initialKey ?? Object.keys(accessors)[0]);
  const [dir, setDir] = useState<Dir>(opts?.initialDir ?? "desc");
  const [page, setPage] = useState(1);

  const sorted = useMemo(() => {
    const get = accessors[sortKey];
    if (!get) return rows;
    const arr = [...rows];
    arr.sort((a, b) => {
      const av = get(a);
      const bv = get(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const c =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv));
      return dir === "asc" ? c : -c;
    });
    return arr;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sortKey, dir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const paged = sorted.slice((safePage - 1) * pageSize, safePage * pageSize);

  const toggle = (key: string) => {
    if (key === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDir("asc");
    }
    setPage(1);
  };

  return { rows: paged, total: sorted.length, sortKey, dir, toggle, page: safePage, setPage, pageCount };
}

export function SortTh({
  label,
  col,
  sortKey,
  dir,
  onSort,
  className,
}: {
  label: string;
  col: string;
  sortKey: string;
  dir: Dir;
  onSort: (k: string) => void;
  className?: string;
}) {
  const active = sortKey === col;
  const Icon = !active ? ChevronsUpDown : dir === "asc" ? ChevronUp : ChevronDown;
  return (
    <th className={clsx("px-4 py-2", className)}>
      <button
        onClick={() => onSort(col)}
        className={clsx(
          "inline-flex items-center gap-1 font-medium",
          active ? "text-ink-900" : "text-ink-500 hover:text-ink-700",
        )}
      >
        {label}
        <Icon className={clsx("h-3.5 w-3.5", active ? "opacity-90" : "opacity-40")} />
      </button>
    </th>
  );
}

export function Pagination({
  page,
  pageCount,
  total,
  onPage,
}: {
  page: number;
  pageCount: number;
  total: number;
  onPage: (p: number) => void;
}) {
  if (pageCount <= 1) return null;
  return (
    <div className="flex items-center justify-between border-t border-[var(--line)] px-4 py-2 text-xs text-ink-500">
      <span>{total} rows</span>
      <span className="flex items-center gap-2">
        <button
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          className="rounded-md border border-[var(--line)] px-2 py-1 disabled:opacity-40 hover:bg-[var(--panel2)]"
        >
          Prev
        </button>
        <span className="text-ink-700">
          {page} / {pageCount}
        </span>
        <button
          disabled={page >= pageCount}
          onClick={() => onPage(page + 1)}
          className="rounded-md border border-[var(--line)] px-2 py-1 disabled:opacity-40 hover:bg-[var(--panel2)]"
        >
          Next
        </button>
      </span>
    </div>
  );
}

// dark tooltip style for Recharts
export const chartTooltip = {
  contentStyle: {
    background: "var(--panel)",
    border: "1px solid var(--line)",
    borderRadius: 8,
    color: "var(--text)",
    fontSize: 12,
  },
  labelStyle: { color: "var(--muted)" },
  itemStyle: { color: "var(--text)" },
};
