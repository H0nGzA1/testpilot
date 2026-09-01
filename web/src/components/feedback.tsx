import clsx from "clsx";
import type { ReactNode } from "react";

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-[var(--panel2)]", className)} />;
}

// a KPI-row + block skeleton used while a page's data loads
export function PageSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-7 w-40" />
      <div className="grid gap-4 sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-56" />
    </div>
  );
}

export function Empty({
  icon,
  title,
  sub,
  action,
}: {
  icon?: ReactNode;
  title: string;
  sub?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-[var(--line)] px-6 py-12 text-center">
      {icon && <div className="text-ink-500">{icon}</div>}
      <div className="text-sm font-medium text-ink-900">{title}</div>
      {sub && <div className="max-w-sm text-sm text-ink-500">{sub}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
