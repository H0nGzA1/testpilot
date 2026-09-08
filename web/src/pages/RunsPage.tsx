import { Fragment, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, relTime, type Run, type TestCase } from "../lib/api";
import { Badge, Button, Card, Checkbox, Input, Select } from "../components/ui";
import { Modal } from "../components/Modal";
import { useToast } from "../components/toast";

// ── date bucketing (grouping key + display order) ──────────────────────────────
const BUCKET_ORDER = ["Today", "Yesterday", "This week", "Earlier"] as const;
function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}
function bucketOf(iso: string | null | undefined, now: Date): string {
  if (!iso) return "Earlier";
  const t = startOfDay(new Date(iso));
  const today = startOfDay(now);
  const day = 86_400_000;
  if (t === today) return "Today";
  if (t === today - day) return "Yesterday";
  if (t > today - 7 * day) return "This week";
  return "Earlier";
}
function fmtDuration(run: Run): string {
  if (!run.started_at || !run.finished_at) return "—";
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`;
}

/** Cases in this run worth re-running: everything the judge didn't pass, plus anything
 *  the run never got a verdict for. Drives the "Re-run failed" button. */
function failedCount(run: Run): number {
  if (run.summary) return run.summary.failed + run.summary.error;
  return Math.max(0, run.total_count - run.passed_count);
}

/** Infra outcomes only — timeouts, dead sessions, crashed browsers. A judge "failed" is a
 *  finding about the product; re-running it proves nothing. Shown as its own button only
 *  when it is a strict subset of the failures, else it duplicates "Re-run failed". */
function errorCount(run: Run): number {
  return run.summary?.error ?? 0;
}

function ResultChips({ run }: { run: Run }) {
  const s = run.summary;
  if (!s) {
    return <span className="text-xs font-semibold text-[var(--ok-fg)]">✓{run.passed_count}</span>;
  }
  return (
    <span className="inline-flex gap-2 text-xs font-semibold">
      <span className="text-[var(--ok-fg)]">✓{s.passed}</span>
      <span className="text-[var(--bad-fg)]">✗{s.failed}</span>
      <span className="text-[var(--warn-fg)]">⚠{s.error}</span>
    </span>
  );
}

export function RunsPage() {
  const pid = Number(useParams().pid);
  const navigate = useNavigate();
  const toast = useToast();
  const { t } = useTranslation();
  const [runs, setRuns] = useState<Run[]>([]);
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [renaming, setRenaming] = useState<{ id: number; value: string } | null>(null);
  const [renameSaving, setRenameSaving] = useState(false);
  const [confirmDel, setConfirmDel] = useState<number[] | null>(null);

  const [cases, setCases] = useState<TestCase[]>([]);
  const load = () => api.listRuns(pid).then(setRuns).catch((e) => toast("error", String(e)));
  useEffect(() => {
    load();
    api.listCases(pid).then(setCases).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  const metrics = useMemo(() => {
    const done = runs.filter((r) => r.summary);
    const avgPass = done.length
      ? Math.round((done.reduce((a, r) => a + (r.summary?.pass_rate ?? 0), 0) / done.length) * 100)
      : 0;
    const durs = done
      .filter((r) => r.started_at && r.finished_at)
      .map((r) => new Date(r.finished_at as string).getTime() - new Date(r.started_at as string).getTime());
    const avgMs = durs.length ? durs.reduce((a, b) => a + b, 0) / durs.length : 0;
    const s = Math.round(avgMs / 1000);
    const avgDur = durs.length ? (s < 60 ? `${s}s` : `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`) : "—";
    const enabled = cases.filter((c) => c.enabled);
    const ran = enabled.filter((c) => c.last_status);
    return {
      total: runs.length,
      done: done.length,
      avgPass,
      avgDur,
      coverage: enabled.length ? Math.round((ran.length / enabled.length) * 100) : 0,
      ranCount: ran.length,
      enabled: enabled.length,
    };
  }, [runs, cases]);

  const active = runs.some((r) => r.status === "pending" || r.status === "running");
  useEffect(() => {
    if (!active) return;
    const iv = setInterval(load, 1500);
    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const filtered = useMemo(
    () =>
      runs.filter((r) => {
        if (status !== "all" && r.status !== status) return false;
        if (q && !r.name.toLowerCase().includes(q.toLowerCase()) && String(r.id) !== q.trim())
          return false;
        return true;
      }),
    [runs, status, q],
  );

  // group by date bucket of started_at (fall back to created_at); newest first inside each group
  const groups = useMemo(() => {
    const now = new Date();
    const by = new Map<string, Run[]>();
    for (const r of filtered) {
      const key = bucketOf(r.started_at ?? r.created_at, now);
      (by.get(key) ?? by.set(key, []).get(key)!).push(r);
    }
    for (const arr of by.values()) arr.sort((a, b) => b.id - a.id);
    return BUCKET_ORDER.filter((k) => by.has(k)).map((k) => ({ bucket: k, rows: by.get(k)! }));
  }, [filtered]);

  const toggle = (id: number) =>
    setSel((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const toggleGroup = (b: string) =>
    setCollapsed((s) => {
      const n = new Set(s);
      n.has(b) ? n.delete(b) : n.add(b);
      return n;
    });

  const saveRename = async (close: () => void) => {
    if (!renaming) return;
    const name = renaming.value.trim();
    if (!name) return;
    setRenameSaving(true);
    try {
      await api.renameRun(renaming.id, name);
      close();
      load();
    } catch (e) {
      toast("error", String(e));
    } finally {
      setRenameSaving(false);
    }
  };

  const doDelete = async (close: () => void) => {
    if (!confirmDel) return;
    try {
      await Promise.all(confirmDel.map((id) => api.deleteRun(id)));
      setSel((s) => {
        const n = new Set(s);
        confirmDel.forEach((id) => n.delete(id));
        return n;
      });
      close();
      load();
    } catch (e) {
      toast("error", String(e));
    }
  };

  const rerun = async (id: number, only?: "failing" | "error") => {
    try {
      const r = await api.rerun(id, only);
      navigate(`/projects/${pid}/runs/${r.id}`);
    } catch (e) {
      toast("error", String(e));
    }
  };
  const cancel = (id: number) => api.cancelRun(id).then(load).catch((e) => toast("error", String(e)));

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-ink-900">{t("Runs")}</h1>
          <p className="mt-1 text-sm text-ink-500">
            {t("Each run executes a batch of cases and produces a report.")} ·{" "}
            {t("{{n}} runs", { n: runs.length })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("Search run name…")}
            className="h-9 max-w-[200px]"
          />
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 w-auto">
            {["all", "running", "completed", "failed", "cancelled"].map((s) => (
              <option key={s} value={s}>
                {s === "all" ? t("All statuses") : t(s)}
              </option>
            ))}
          </Select>
          {sel.size >= 2 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/projects/${pid}/compare?runs=${[...sel].join(",")}`)}
            >
              {t("Compare ({{n}})", { n: sel.size })}
            </Button>
          )}
          {sel.size > 0 && (
            <Button variant="danger" size="sm" onClick={() => setConfirmDel([...sel])}>
              {t("Delete ({{n}})", { n: sel.size })}
            </Button>
          )}
        </div>
      </div>

      {runs.length > 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Card className="p-4">
            <div className="text-xs text-ink-500">{t("Total runs")}</div>
            <div className="mt-1 text-2xl font-semibold text-ink-900">{metrics.total}</div>
            <div className="mt-1 text-[11.5px] text-ink-500">{t("{{n}} completed", { n: metrics.done })}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs text-ink-500">{t("Avg pass rate")}</div>
            <div className="mt-1 text-2xl font-semibold text-ink-900">{metrics.done ? `${metrics.avgPass}%` : "—"}</div>
            <div className="mt-1 text-[11.5px] text-ink-500">{t("across completed runs")}</div>
          </Card>
          <Card className="flex items-center justify-between p-4">
            <div>
              <div className="text-xs text-ink-500">{t("Suite coverage")}</div>
              <div className="mt-1 text-2xl font-semibold text-ink-900">{metrics.enabled ? `${metrics.coverage}%` : "—"}</div>
              <div className="mt-1 text-[11.5px] text-ink-500">
                {t("{{r}}/{{e}} cases", { r: metrics.ranCount, e: metrics.enabled })}
              </div>
            </div>
            {metrics.enabled > 0 && (
              <div
                className="relative h-[46px] w-[46px] flex-none rounded-full"
                style={{ background: `conic-gradient(var(--ok) ${metrics.coverage}%, var(--panel2) 0)` }}
              >
                <div className="absolute inset-[7px] rounded-full bg-[var(--panel)]" />
              </div>
            )}
          </Card>
          <Card className="p-4">
            <div className="text-xs text-ink-500">{t("Avg duration")}</div>
            <div className="mt-1 text-2xl font-semibold text-ink-900">{metrics.avgDur}</div>
            <div className="mt-1 text-[11.5px] text-ink-500">{t("per run")}</div>
          </Card>
        </div>
      )}

      {filtered.length === 0 ? (
        <Card className="px-4 py-10 text-center text-sm text-ink-500">
          {runs.length === 0
            ? t(
                "No runs yet. A run executes a batch of cases and produces a video, a step-by-step trace and a pass/fail verdict for each. Go to Test Cases and click “Run all enabled”.",
              )
            : t("No runs match this filter.")}
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-[var(--line)] text-left text-xs text-ink-500">
              <tr>
                <th className="w-9 px-3 py-2" />
                <th className="px-4 py-2">{t("Run")}</th>
                <th className="px-4 py-2">{t("Status")}</th>
                <th className="px-4 py-2">{t("Progress")}</th>
                <th className="px-4 py-2">{t("Result")}</th>
                <th className="px-4 py-2">{t("Cases")}</th>
                <th className="px-4 py-2">{t("Duration")}</th>
                <th className="px-4 py-2">{t("Started")}</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {groups.map(({ bucket, rows }) => {
                const open = !collapsed.has(bucket);
                return (
                  <Fragment key={bucket}>
                    <tr className="bg-[var(--panel2)]">
                      <td colSpan={9} className="px-3 py-2">
                        <button
                          onClick={() => toggleGroup(bucket)}
                          className="flex items-center gap-2 text-xs font-semibold text-ink-900"
                        >
                          <span className={"w-3 text-ink-500 transition-transform " + (open ? "rotate-90" : "")}>›</span>
                          {t(bucket)}
                          <span className="rounded-full bg-[var(--panel)] px-1.5 py-0.5 text-[11px] font-normal text-ink-500">
                            {rows.length}
                          </span>
                        </button>
                      </td>
                    </tr>
                    {open &&
                      rows.map((r) => {
                        const running = r.status === "running" || r.status === "pending";
                        const pct = r.total_count ? (r.processed_count / r.total_count) * 100 : 0;
                        return (
                          <tr key={r.id} className="border-b border-[var(--line)] last:border-0 hover:bg-brand-50/40">
                            <td className="px-3 py-2">
                              <Checkbox checked={sel.has(r.id)} onChange={() => toggle(r.id)} />
                            </td>
                            <td className="px-4 py-2">
                              <div className="flex items-center gap-1.5">
                                <Link
                                  to={`/projects/${pid}/runs/${r.id}`}
                                  className="font-medium text-ink-900 hover:text-brand-700"
                                >
                                  {r.name}
                                </Link>
                                <button
                                  className="text-ink-400 hover:text-brand-700"
                                  title={t("Rename")}
                                  onClick={() => setRenaming({ id: r.id, value: r.name })}
                                >
                                  ✎
                                </button>
                              </div>
                              <div className="text-xs text-ink-500">
                                #{r.id}
                                {r.created_by ? ` · ${r.created_by}` : ""}
                              </div>
                            </td>
                            <td className="px-4 py-2">
                              {running ? (
                                <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
                                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-600" />
                                  {t(r.status)}
                                </span>
                              ) : (
                                <Badge status={r.status} />
                              )}
                            </td>
                            <td className="px-4 py-2">
                              <div className="flex items-center gap-2">
                                <span className="inline-block h-1.5 w-[72px] overflow-hidden rounded-full bg-[var(--panel2)]">
                                  <span
                                    className="block h-full rounded-full bg-brand-600"
                                    style={{ width: `${pct}%` }}
                                  />
                                </span>
                                <span className="text-xs text-ink-500">
                                  {r.processed_count}/{r.total_count}
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-2">
                              <ResultChips run={r} />
                            </td>
                            <td className="px-4 py-2 text-ink-700">{r.total_count}</td>
                            <td className="px-4 py-2 text-ink-700">{fmtDuration(r)}</td>
                            <td className="px-4 py-2 text-ink-500">{relTime(r.started_at ?? r.created_at)}</td>
                            <td className="px-4 py-2 text-right">
                              <div className="flex justify-end gap-1">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => navigate(`/projects/${pid}/runs/${r.id}`)}
                                >
                                  {t("View")}
                                </Button>
                                {running ? (
                                  <Button size="sm" variant="outline" onClick={() => cancel(r.id)}>
                                    {t("Cancel")}
                                  </Button>
                                ) : (
                                  <>
                                    {failedCount(r) > 0 && (
                                      <Button size="sm" variant="outline" onClick={() => rerun(r.id, "failing")}>
                                        {t("Re-run failed ({{n}})", { n: failedCount(r) })}
                                      </Button>
                                    )}
                                    {errorCount(r) > 0 && errorCount(r) < failedCount(r) && (
                                      <Button size="sm" variant="outline" onClick={() => rerun(r.id, "error")}>
                                        {t("Re-run errors ({{n}})", { n: errorCount(r) })}
                                      </Button>
                                    )}
                                    <Button size="sm" variant="outline" onClick={() => rerun(r.id)}>
                                      {t("Re-run")}
                                    </Button>
                                  </>
                                )}
                                <Button size="sm" variant="danger" onClick={() => setConfirmDel([r.id])}>
                                  {t("Delete")}
                                </Button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
      <p className="text-xs text-ink-500">{t("{{n}} runs · grouped by start date", { n: filtered.length })}</p>

      {renaming && (
        <Modal onClose={() => setRenaming(null)} className="max-w-md">
          {(close) => (
            <Card className="space-y-4 p-5">
              <h2 className="text-base font-semibold text-ink-900">{t("Rename run")}</h2>
              <Input
                autoFocus
                value={renaming.value}
                onChange={(e) => setRenaming((m) => (m ? { ...m, value: e.target.value } : m))}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveRename(close);
                }}
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={close}>
                  {t("Cancel")}
                </Button>
                <Button onClick={() => saveRename(close)} disabled={renameSaving}>
                  {renameSaving ? t("Saving…") : t("Save changes")}
                </Button>
              </div>
            </Card>
          )}
        </Modal>
      )}

      {confirmDel && (
        <Modal onClose={() => setConfirmDel(null)} className="max-w-md">
          {(close) => (
            <Card className="space-y-4 p-5">
              <h2 className="text-base font-semibold text-ink-900">{t("Delete run(s)?")}</h2>
              <p className="text-sm text-ink-500">
                {t("This permanently removes {{n}} run(s) and their results. This cannot be undone.", {
                  n: confirmDel.length,
                })}
              </p>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={close}>
                  {t("Cancel")}
                </Button>
                <Button variant="danger" onClick={() => doDelete(close)}>
                  {t("Delete")}
                </Button>
              </div>
            </Card>
          )}
        </Modal>
      )}
    </div>
  );
}
