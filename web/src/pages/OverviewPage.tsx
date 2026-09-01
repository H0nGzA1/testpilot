import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, relTime, type ProjectStats } from "../lib/api";
import { Badge, Button, Card } from "../components/ui";
import { chartTooltip } from "../components/table";
import { Empty, PageSkeleton } from "../components/feedback";
import { SetupChecklist } from "../components/SetupChecklist";

export function OverviewPage() {
  const { t } = useTranslation();
  const pid = Number(useParams().pid);
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.getStats(pid).then(setStats).catch((e) => setErr(String(e)));
  }, [pid]);

  if (err) return <div className="rounded-lg bg-[var(--bad-bg)] px-3 py-2 text-sm text-[var(--bad-fg)]">{err}</div>;
  if (!stats) return <PageSkeleton />;

  const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  const trendData = stats.trend.map((t, i) => ({
    x: t.name?.slice(0, 12) || `#${t.run_id}`,
    pass: Math.round(t.pass_rate * 100),
    i,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">{t("Overview")}</h1>
        <p className="mt-1 text-sm text-ink-500">{t("Suite health at a glance.")}</p>
      </div>

      <SetupChecklist pid={pid} stats={stats} />

      <div className="grid gap-4 sm:grid-cols-4">
        <Tile label={t("Test cases")} value={`${stats.enabled_count}/${stats.case_count}`} sub={t("enabled / total")} />
        <Tile label={t("Last pass rate")} value={pct(stats.last_pass_rate)} />
        <Tile
          label={t("Last p50 latency")}
          value={stats.last_latency_p50_ms != null ? `${(stats.last_latency_p50_ms / 1000).toFixed(1)}s` : "—"}
        />
        <Tile label={t("Flaky (last run)")} value={String(stats.last_flaky)} />
      </div>

      {stats.run_count === 0 ? (
        <Empty
          title={t("No runs yet")}
          sub={t("Add test cases, then run them to see pass-rate trends and suite health here.")}
          action={
            <Link to={`/projects/${pid}/cases`}>
              <Button size="sm">{t("Go to Test Cases →")}</Button>
            </Link>
          }
        />
      ) : (
        <>
          <Card className="p-4">
            <div className="mb-3 text-sm font-medium text-ink-900">{t("Pass rate over runs")}</div>
            {trendData.length >= 2 ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={trendData} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.3 0.01 250)" vertical={false} />
                  <XAxis dataKey="x" tick={{ fontSize: 11, fill: "oklch(0.68 0.012 250)" }} tickLine={false} />
                  <YAxis
                    domain={[0, 100]}
                    tickFormatter={(v) => `${v}%`}
                    tick={{ fontSize: 11, fill: "oklch(0.68 0.012 250)" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip formatter={(v) => [`${v}%`, "pass rate"]} {...chartTooltip} />
                  <Line
                    type="monotone"
                    dataKey="pass"
                    stroke="oklch(0.72 0.16 250)"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="py-10 text-center text-sm text-ink-500">
                {t("Need at least two completed runs to draw a trend.")}
              </div>
            )}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-medium text-ink-900">{t("Recent runs")}</div>
                <Link to={`/projects/${pid}/runs`} className="text-sm text-brand-700 hover:underline">
                  {t("View all")}
                </Link>
              </div>
              {stats.last_run ? (
                <div className="divide-y divide-[var(--line)]">
                  {[stats.last_run].map((r) => (
                    <Link
                      key={r.id}
                      to={`/projects/${pid}/runs/${r.id}`}
                      className="flex items-center justify-between py-2 text-sm hover:text-brand-700"
                    >
                      <span className="text-ink-900">{r.name}</span>
                      <span className="flex items-center gap-3">
                        <span className="text-ink-500">
                          {r.summary ? `${Math.round(r.summary.pass_rate * 100)}%` : `${r.processed_count}/${r.total_count}`}
                        </span>
                        <Badge status={r.status} />
                        <span className="text-xs text-ink-500">{relTime(r.started_at)}</span>
                      </span>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="py-6 text-center text-sm text-ink-500">{t("No runs.")}</div>
              )}
            </Card>

            <Card className="p-4">
              <div className="mb-3 text-sm font-medium text-ink-900">{t("Top failing cases")}</div>
              {stats.top_failing.length === 0 ? (
                <div className="py-6 text-center text-sm text-ink-500">{t("Nothing failing. Nice.")}</div>
              ) : (
                <div className="divide-y divide-[var(--line)]">
                  {stats.top_failing.map((c) => (
                    <div key={c.case_id} className="flex items-center justify-between py-2 text-sm">
                      <span className="truncate text-ink-900">{c.name}</span>
                      <span className="shrink-0 rounded-full bg-[var(--bad-bg)] px-2 py-0.5 text-xs font-medium text-[var(--bad-fg)]">
                        {t("{{n}} fails", { n: c.fail_count })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-ink-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink-900">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-ink-500">{sub}</div>}
    </Card>
  );
}
