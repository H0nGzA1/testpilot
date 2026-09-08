import { Loader2, Square } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { MediaPlayer, MediaProvider } from "@vidstack/react";
import { DefaultVideoLayout, defaultLayoutIcons } from "@vidstack/react/player/layouts/default";
import "@vidstack/react/player/styles/default/theme.css";
import "@vidstack/react/player/styles/default/layouts/video.css";
import { api, type Run, type RunResult, type TestCase } from "../lib/api";
import { Badge, Button, Card, Input } from "../components/ui";
import { Modal } from "../components/Modal";
import { ShotViewer } from "../components/ShotViewer";
import { chartTooltip } from "../components/table";
import { useToast } from "../components/toast";

const COLORS: Record<string, string> = {
  passed: "oklch(0.6 0.17 150)",
  failed: "oklch(0.58 0.22 25)",
  error: "oklch(0.7 0.17 70)",
};
const PRIORITY_STYLE: Record<string, string> = {
  P0: "bg-[var(--bad-bg)] text-[var(--bad-fg)]",
  P1: "bg-[var(--warn-bg)] text-[var(--warn-fg)]",
  P2: "bg-[var(--panel2)] text-ink-700",
  P3: "bg-[var(--panel2)] text-ink-500",
};

function fmtDur(a: string | null | undefined, b: string | null | undefined): string | null {
  if (!a || !b) return null;
  const s = Math.max(0, Math.round((new Date(b).getTime() - new Date(a).getTime()) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`;
}
function fmtClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}

const FILTERS = [
  { key: "all", label: "All" },
  { key: "failing", label: "Failing only" },
  { key: "passed", label: "passed" },
  { key: "error", label: "error" },
] as const;

export function RunReport() {
  const { rid, pid } = useParams();
  const runId = Number(rid);
  const navigate = useNavigate();
  const toast = useToast();
  const { t } = useTranslation();
  const [run, setRun] = useState<Run | null>(null);
  const [results, setResults] = useState<RunResult[]>([]);
  const [cases, setCases] = useState<TestCase[]>([]);
  const [envName, setEnvName] = useState<string | null>(null);
  const [selected, setSelected] = useState<RunResult | null>(null);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);
  const [liveShot, setLiveShot] = useState<number | null>(null);
  const [cancelling, setCancelling] = useState(false);
  // step whose screenshot the live pane shows; null = follow the newest one
  const [pinnedStep, setPinnedStep] = useState<number | null>(null);

  useEffect(() => {
    const es = new EventSource(api.streamUrl(runId));
    es.addEventListener("progress", (e) => setRun(JSON.parse((e as MessageEvent).data)));
    const poll = setInterval(() => api.getResults(runId).then(setResults), 1500);
    api.getRun(runId).then((r) => {
      setRun(r);
      if (r.environment_id != null && pid) {
        api
          .listEnvironments(Number(pid))
          .then((es) => setEnvName(es.find((e) => e.id === r.environment_id)?.name ?? null))
          .catch(() => {});
      }
    });
    api.getResults(runId).then(setResults);
    return () => {
      es.close();
      clearInterval(poll);
    };
  }, [runId]);
  useEffect(() => {
    if (pid) api.listCases(Number(pid)).then(setCases).catch(() => {});
  }, [pid]);

  const caseById = useMemo(() => new Map(cases.map((c) => [c.id, c] as const)), [cases]);
  const s = run?.summary;
  const chartData = s
    ? [
        { name: "passed", value: s.passed },
        { name: "failed", value: s.failed },
        { name: "error", value: s.error },
      ].filter((d) => d.value > 0)
    : [];
  const duration = fmtDur(run?.started_at, run?.finished_at);

  const active = run?.status === "running" || run?.status === "pending";

  // First-run coaching. A first run is slow (real browser + recording) and its report is
  // the first one anyone reads, so it gets a "this is normal" hint while nothing has
  // finished yet, and a what-now card at the end. Both self-retire: the hint as soon as
  // a result lands, the card once the project has more than one run.
  const [isFirstRun, setIsFirstRun] = useState(false);
  useEffect(() => {
    if (!pid || active) return;
    api
      .getStats(Number(pid))
      .then((st) => setIsFirstRun(st.run_count <= 1))
      .catch(() => {});
  }, [pid, active]);
  // merge case_ids with result rows so pending cases show; running cases now have real
  // rows (status "running") carrying a live-growing step timeline.
  const rows = useMemo(() => {
    const byId = new Map(results.map((r) => [r.case_id, r] as const));
    const ids = run?.case_ids ?? [];
    if (!ids.length) return results.map((r) => ({ case_id: r.case_id, status: r.status, r }));
    return ids.map((id) => {
      const r = byId.get(id);
      if (r) return { case_id: id, status: r.status, r };
      return { case_id: id, status: "pending" as const, r: undefined };
    });
  }, [results, run]);
  const runningIds = rows.filter((x) => x.status === "running").map((x) => x.case_id);
  const counts = useMemo(() => {
    const c = { passed: 0, failed: 0, error: 0, running: 0, pending: 0 };
    for (const x of rows) (c as Record<string, number>)[x.status] = ((c as Record<string, number>)[x.status] ?? 0) + 1;
    return c;
  }, [rows]);
  const total = rows.length;
  const liveRow = active ? results.find((r) => r.status === "running") : undefined;
  const liveShots = (liveRow?.diagnostics ?? []).filter((d) => d.screenshot);
  // -1 when the pinned step has no shot (or vanished with a new case) => fall back to newest
  const pinnedIdx = pinnedStep === null ? -1 : liveShots.findIndex((s) => s.i === pinnedStep);
  const shownIdx = pinnedIdx >= 0 ? pinnedIdx : liveShots.length - 1;
  const shownStep = liveShots[shownIdx];
  const filtered = useMemo(
    () =>
      rows.filter((x) => {
        if (filter === "failing" && !(x.status === "failed" || x.status === "error")) return false;
        if (filter === "passed" && x.status !== "passed") return false;
        if (filter === "error" && x.status !== "error") return false;
        if (q) {
          const c = caseById.get(x.case_id);
          const hay = `${c?.case_key ?? ""} ${c?.name ?? ""} #${x.case_id}`.toLowerCase();
          if (!hay.includes(q.toLowerCase())) return false;
        }
        return true;
      }),
    [rows, filter, q, caseById],
  );
  const latencyData = results
    .filter((r) => r.status === "passed" || r.status === "failed" || r.status === "error")
    .map((r) => ({
      x: caseById.get(r.case_id)?.case_key ?? `#${r.case_id}`,
      s: +(r.latency_ms / 1000).toFixed(1),
      status: r.status,
    }));

  const createIssue = async (r: RunResult) => {
    try {
      const c = caseById.get(r.case_id);
      const issue = await api.createIssue(Number(pid), {
        title: `${c?.name ?? `Case #${r.case_id}`} ${r.status}`,
        description: r.judge_reason ?? r.error ?? "",
        severity: "high",
        case_id: r.case_id,
        run_id: runId,
        result_id: r.id,
      });
      toast("success", `Issue #${issue.id} created`);
      navigate(`/projects/${pid}/issues`);
    } catch (e) {
      toast("error", String(e));
    }
  };

  const rerun = async (only?: "failing" | "error") => {
    try {
      const nr = await api.rerun(runId, only);
      toast(
        "success",
        only === "error"
          ? t("Re-running the errored cases")
          : only === "failing"
            ? t("Re-running the failed cases")
            : t("Re-running the same suite"),
      );
      navigate(`/projects/${pid}/runs/${nr.id}`);
    } catch (e) {
      toast("error", String(e));
    }
  };
  const doDelete = async (close: () => void) => {
    try {
      await api.deleteRun(runId);
      close();
      navigate(`/projects/${pid}/runs`);
    } catch (e) {
      toast("error", String(e));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link to={pid ? `/projects/${pid}/runs` : "/"} className="text-sm text-ink-500 hover:text-ink-900">
          {t("← Runs")}
        </Link>
        <h1 className="text-xl font-semibold text-ink-900">{run?.name ?? `Run #${runId}`}</h1>
        {run && <Badge status={run.status} />}
        {run && (
          <span className="text-xs text-ink-500">
            {duration ? `${t("Duration")} ${duration} · ` : ""}
            {fmtClock(run.started_at)}
            {run.finished_at ? ` → ${fmtClock(run.finished_at)}` : ""} · {t("Concurrency")} {run.concurrency}
            {run.ran_by_label ? ` · ${t("run by")} ${run.ran_by_label}` : ""}
            {envName ? ` · 🌐 ${envName}` : ""}
          </span>
        )}
        <div className="ml-auto flex gap-2">
          {run && !active && (
            <a href={api.runExportUrl(runId)}>
              <Button size="sm" variant="outline">
                {t("Export CSV")}
              </Button>
            </a>
          )}
          {active && (
            <Button
              size="sm"
              variant="danger"
              disabled={cancelling}
              onClick={() => {
                setCancelling(true);
                api
                  .cancelRun(runId)
                  .then(() => toast("info", t("Cancelling — cases stop after the current step")))
                  .catch(() => {
                    setCancelling(false);
                    toast("error", t("Could not cancel the run"));
                  });
              }}
            >
              {cancelling ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  {t("Cancelling…")}
                </>
              ) : (
                <>
                  <Square size={12} />
                  {t("Stop run")}
                </>
              )}
            </Button>
          )}
          {run && !active && counts.failed + counts.error > 0 && (
            <Button size="sm" onClick={() => rerun("failing")}>
              {t("Re-run failed ({{n}})", { n: counts.failed + counts.error })}
            </Button>
          )}
          {run && !active && counts.error > 0 && counts.failed > 0 && (
            <Button size="sm" variant="outline" onClick={() => rerun("error")}>
              {t("Re-run errors ({{n}})", { n: counts.error })}
            </Button>
          )}
          {run && !active && (
            <Button size="sm" variant="outline" onClick={() => rerun()}>
              {t("Re-run this suite")}
            </Button>
          )}
          {run && !active && (
            <Button size="sm" variant="danger" onClick={() => setConfirmDel(true)}>
              {t("Delete")}
            </Button>
          )}
        </div>
      </div>

      {active && counts.passed + counts.failed + counts.error === 0 && (
        <div className="rounded-xl border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-ink-700">
          {t("Nothing has finished yet — that's expected. Each case launches a real Chrome, drives it and records video, so the first result takes roughly 30–90 seconds. Results stream in below as they land; you can leave this page.")}
        </div>
      )}

      {!active && isFirstRun && s && s.total > 0 && (
        <div className="rounded-xl border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-ink-700">
          <div className="font-medium text-ink-900">{t("Your first report — what now?")}</div>
          {s.failed + s.error === 0 ? (
            <div className="mt-1">
              {t("Everything passed. Save these cases as a suite and give it a schedule, and this becomes a regression run that happens without you.")}{" "}
              <Link to={`/projects/${pid}/suites`} className="font-medium text-brand-700 hover:underline">
                {t("Create a suite →")}
              </Link>
            </div>
          ) : (
            <div className="mt-1">
              {t("{{n}} case(s) did not pass. The Reason column has the judge's verdict; “Replay” plays back the video and the agent's steps so you can see where it went wrong, and “+ Issue” turns it into a tracked issue.", {
                n: s.failed + s.error,
              })}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Tile
          label={t("Pass rate")}
          value={s ? `${Math.round(s.pass_rate * 100)}%` : "—"}
          sub={s ? t("{{p}}/{{n}} passed", { p: s.passed, n: s.total }) : t("computed when done")}
        />
        <Tile
          label={t("Progress")}
          value={run ? `${run.processed_count}/${run.total_count}` : "—"}
          sub={
            active
              ? runningIds.length
                ? t("{{n}} running", { n: runningIds.length })
                : t("in progress")
              : t("done")
          }
        />
        <Tile
          label={t("Duration")}
          value={duration ?? (active && run?.started_at ? fmtDur(run.started_at, new Date().toISOString()) ?? "—" : "—")}
          sub={
            !active && duration
              ? `${fmtClock(run?.started_at)} → ${fmtClock(run?.finished_at)}`
              : active
                ? t("elapsed · running")
                : ""
          }
        />
        <Tile
          label={t("Flaky")}
          value={s ? String(s.flaky) : "—"}
          sub={s ? (s.flaky > 0 ? t("passed after retry") : t("none")) : t("computed when done")}
        />
      </div>

      {active && (
        <Card className="p-4">
          <div className="flex items-center gap-2">
            <div className="text-sm font-medium text-ink-900">{t("Run progress")}</div>
            {runningIds.length > 0 && (
              <span
                className="flex min-w-0 items-center gap-1.5 truncate text-xs text-ink-500"
                title={runningIds.map((i) => `#${i}`).join(", ")}
              >
                <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-brand-600" />
                {t("{{n}} running", { n: runningIds.length })}
              </span>
            )}
            <span className="ml-auto text-xl font-semibold text-ink-900">
              {run?.processed_count ?? 0}/{total}{" "}
              <span className="text-xs font-normal text-ink-500">
                · {total ? Math.round(((run?.processed_count ?? 0) / total) * 100) : 0}%
              </span>
            </span>
          </div>
          <div className="my-3 flex h-3.5 overflow-hidden rounded-lg bg-[var(--panel2)]">
            <span style={{ width: `${total ? (counts.passed / total) * 100 : 0}%`, background: "var(--ok-fg)" }} />
            <span style={{ width: `${total ? (counts.failed / total) * 100 : 0}%`, background: "var(--bad-fg)" }} />
            <span style={{ width: `${total ? (counts.error / total) * 100 : 0}%`, background: "var(--warn-fg)" }} />
            <span
              className="animate-pulse"
              style={{ width: `${total ? (counts.running / total) * 100 : 0}%`, background: "var(--brand-600)" }}
            />
          </div>
          <div className="flex flex-wrap gap-4 text-[13px] text-ink-700">
            {(
              [
                ["passed", "var(--ok-fg)"],
                ["failed", "var(--bad-fg)"],
                ["error", "var(--warn-fg)"],
                ["running", "var(--brand-600)"],
                ["pending", "var(--line)"],
              ] as const
            ).map(([k, col]) => (
              <span key={k} className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-[2px]" style={{ background: col }} />
                {t(k)} <b className="text-ink-900">{counts[k]}</b>
              </span>
            ))}
          </div>
        </Card>
      )}

      {liveShot !== null && liveShots.length > 0 && (
        <ShotViewer shots={liveShots} index={liveShot} onIndex={setLiveShot} onClose={() => setLiveShot(null)} />
      )}

      {active && liveRow && (
        <Card className="p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="text-sm font-medium text-ink-900">{t("Live execution")}</div>
            <span className="text-xs text-ink-500">
              {caseById.get(liveRow.case_id)?.name ?? `#${liveRow.case_id}`}
              {caseById.get(liveRow.case_id)?.case_key ? ` · ${caseById.get(liveRow.case_id)?.case_key}` : ""}
            </span>
            {liveRow.diagnostics && liveRow.diagnostics.length > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-600" />
                {t("Step {{n}}", { n: liveRow.diagnostics.length })}
              </span>
            )}
            {pinnedIdx >= 0 && (
              <button
                onClick={() => setPinnedStep(null)}
                className="rounded-full border border-[var(--line)] px-2 py-0.5 text-xs text-ink-700 hover:bg-brand-50"
              >
                {t("showing step {{n}} · back to latest", { n: pinnedStep })}
              </button>
            )}
          </div>
          <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
            <div className="overflow-hidden rounded-xl border border-[var(--line)]">
              {shownStep ? (
                // cropped to 16/10 here — click through for the whole page at full size
                <button
                  onClick={() => setLiveShot(shownIdx)}
                  title={t("click to enlarge")}
                  className="block w-full cursor-zoom-in"
                >
                  <img
                    src={shownStep.screenshot!}
                    alt={`step ${shownStep.i}`}
                    className="aspect-[16/10] w-full bg-white object-cover object-top"
                  />
                </button>
              ) : (
                <div className="grid aspect-[16/10] place-items-center bg-[var(--panel2)] text-sm text-ink-500">
                  {t("waiting for first screenshot…")}
                </div>
              )}
            </div>
            <div className="max-h-[340px] overflow-auto">
              {(liveRow.diagnostics ?? []).map((step, i, arr) => {
                const isLast = i === arr.length - 1;
                const isShown = shownStep?.i === step.i;
                return (
                  <button
                    key={step.i}
                    onClick={() => setPinnedStep(step.i)}
                    disabled={!step.screenshot}
                    title={step.screenshot ? t("click a step to see its screenshot") : undefined}
                    className={
                      "grid w-full grid-cols-[22px_1fr] gap-2.5 border-b border-[var(--line)] px-1.5 py-2 text-left last:border-0 " +
                      (step.screenshot ? "cursor-pointer hover:bg-brand-50/60 " : "") +
                      (isShown ? "bg-brand-50" : "")
                    }
                  >
                    <div
                      className={
                        "grid h-[20px] w-[20px] place-items-center rounded-full text-[10px] font-bold text-[var(--on-brand)] " +
                        (isLast ? "bg-brand-600" : "bg-[var(--ok-fg)]")
                      }
                    >
                      {step.i}
                    </div>
                    <div className="min-w-0">
                      <div className="mb-0.5">
                        <span className="rounded bg-brand-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-brand-700">
                          {step.action}
                        </span>
                      </div>
                      {step.thought && (
                        <div className="text-[12.5px] leading-snug text-ink-700">
                          <span className="mr-1 text-ink-500">💭</span>
                          {step.thought}
                        </div>
                      )}
                      {isLast && (
                        <div className="mt-1 flex items-center gap-1.5 text-xs text-brand-700">
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-600" />
                          {t("running…")}
                        </div>
                      )}
                    </div>
                  </button>
                );
              })}
              {(liveRow.diagnostics ?? []).length === 0 && (
                <div className="py-6 text-center text-xs text-ink-500">{t("executing…")}</div>
              )}
            </div>
          </div>
        </Card>
      )}

      <Card className="overflow-x-auto">
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
            <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-ink-900">
              {t("Cases")}
              <span className="text-xs font-normal text-ink-500">{rows.length}</span>
              {runningIds.length > 0 && (
                <span
                  className="flex min-w-0 items-center gap-1.5 truncate text-xs font-normal text-ink-500"
                  title={runningIds.map((i) => `#${i}`).join(", ")}
                >
                  <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-brand-600" />
                  {t("{{n}} running", { n: runningIds.length })}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t("Search case…")}
                className="h-8 max-w-[160px] text-xs"
              />
              <div className="inline-flex overflow-hidden rounded-lg border border-[var(--line)]">
                {FILTERS.map((f) => (
                  <button
                    key={f.key}
                    onClick={() => setFilter(f.key)}
                    className={
                      "border-r border-[var(--line)] px-2.5 py-1 text-xs last:border-r-0 " +
                      (filter === f.key ? "bg-brand-600 text-[var(--on-brand)]" : "text-ink-700 hover:text-ink-900")
                    }
                  >
                    {t(f.label)}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <table className="w-full text-sm">
            <thead className="border-y border-[var(--line)] text-left text-xs text-ink-500">
              <tr>
                <th className="px-4 py-2">{t("Case")}</th>
                <th className="px-3 py-2">{t("Module")}</th>
                <th className="px-3 py-2">{t("Priority")}</th>
                <th className="px-3 py-2">{t("Status")}</th>
                <th className="px-3 py-2">{t("Attempts")}</th>
                <th className="px-3 py-2">{t("Latency")}</th>
                <th className="px-4 py-2">{t("Judge")}</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((x) => {
                const r = x.r;
                const done = !!r && x.status !== "running";
                const c = caseById.get(x.case_id);
                return (
                  <tr key={x.case_id} className="border-b border-[var(--line)] last:border-0 hover:bg-brand-50/40">
                    <td className="max-w-[300px] px-4 py-2">
                      <div className="truncate font-medium text-ink-900" title={c?.name ?? ""}>
                        {c?.name ?? `#${x.case_id}`}
                      </div>
                      <div className="font-mono text-[11px] text-ink-500">{c?.case_key ?? `#${x.case_id}`}</div>
                      {r?.account_label && (
                        <div className="mt-0.5 text-[11px] text-brand-700">👤 {r.account_label}</div>
                      )}
                    </td>
                    <td className="max-w-[110px] truncate px-3 py-2 text-ink-500" title={c?.module ?? ""}>
                      {c?.module ?? "—"}
                    </td>
                    <td className="px-3 py-2">
                      {c ? (
                        <span
                          className={"inline-flex rounded px-1.5 py-0.5 text-[11px] font-semibold " + (PRIORITY_STYLE[c.priority] ?? "")}
                        >
                          {c.priority}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="space-x-1 px-3 py-2">
                      {x.status === "running" ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-600" />
                          {t("running")}
                        </span>
                      ) : (
                        <Badge status={x.status}>{x.status === "pending" ? t("pending") : undefined}</Badge>
                      )}
                      {r?.flaky && <Badge status="flaky">flaky</Badge>}
                    </td>
                    <td className="px-3 py-2 text-ink-700">{done ? (r!.flaky ? `×${r!.attempts}` : r!.attempts) : "—"}</td>
                    <td className="px-3 py-2 text-ink-700">{done ? `${(r!.latency_ms / 1000).toFixed(1)}s` : "—"}</td>
                    <td className="max-w-[160px] truncate px-4 py-2 text-ink-700" title={r?.judge_reason ?? r?.error ?? ""}>
                      {done ? (r!.judge_reason ?? r!.error ?? "—") : x.status === "running" ? t("executing…") : "—"}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {done && (
                        <div className="flex justify-end gap-1">
                          {(r!.status === "failed" || r!.status === "error") && (
                            <Button size="sm" variant="outline" onClick={() => createIssue(r!)}>
                              {t("+ Issue")}
                            </Button>
                          )}
                          <Button size="sm" variant="outline" onClick={() => setSelected(r!)}>
                            {t("Replay")}
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-ink-500">
                    {run?.status === "running" ? t("executing…") : t("no results")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>

      {!active && (
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="p-4">
          <div className="mb-2 text-sm font-medium text-ink-900">{t("Outcome")}</div>
          {chartData.length ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={chartData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80}>
                  {chartData.map((d) => (
                    <Cell key={d.name} fill={COLORS[d.name]} />
                  ))}
                </Pie>
                <Tooltip {...chartTooltip} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="grid h-[200px] place-items-center text-sm text-ink-500">
              {run?.status === "running" ? t("running…") : t("no data")}
            </div>
          )}
        </Card>

        {latencyData.length > 0 && (
          <Card className="p-4 lg:col-span-2">
            <div className="mb-3 text-sm font-medium text-ink-900">{t("Latency by case (s)")}</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={latencyData} margin={{ top: 4, right: 12, bottom: 0, left: -20 }}>
                <XAxis dataKey="x" tick={{ fontSize: 11, fill: "oklch(0.55 0.015 250)" }} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "oklch(0.55 0.015 250)" }} tickLine={false} axisLine={false} />
                <Tooltip formatter={(v) => [`${v}s`, "latency"]} {...chartTooltip} />
                <Bar dataKey="s" radius={[3, 3, 0, 0]}>
                  {latencyData.map((d, i) => (
                    <Cell key={i} fill={COLORS[d.status] ?? "oklch(0.52 0.21 250)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        )}
      </div>
      )}

      {selected && <ReplayPanel result={selected} caseName={caseById.get(selected.case_id)?.name} onClose={() => setSelected(null)} />}

      {confirmDel && (
        <Modal onClose={() => setConfirmDel(false)} className="max-w-md">
          {(close) => (
            <Card className="space-y-4 p-5">
              <h2 className="text-base font-semibold text-ink-900">{t("Delete run(s)?")}</h2>
              <p className="text-sm text-ink-500">
                {t("This permanently removes {{n}} run(s) and their results. This cannot be undone.", { n: 1 })}
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

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-ink-500">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold text-ink-900">{value}</div>
      {sub ? <div className="mt-1.5 text-[11.5px] text-ink-500">{sub}</div> : null}
    </Card>
  );
}

function ReplayPanel({
  result,
  caseName,
  onClose,
}: {
  result: RunResult;
  caseName?: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [rawOpen, setRawOpen] = useState(false);
  const [shotIdx, setShotIdx] = useState<number | null>(null);
  const diag = result.diagnostics ?? [];
  const shots = diag.filter((d) => d.screenshot);
  return (
    <Modal onClose={onClose} className="max-w-3xl">
      {(close) => (
        <Card className="max-h-[85vh] overflow-auto p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-medium text-ink-900">
                {caseName ?? t("Case #{{id}} replay", { id: result.case_id })}
              </span>
              <Badge status={result.status} />
              {result.flaky && <Badge status="flaky">flaky ×{result.attempts}</Badge>}
            </div>
            <Button size="sm" variant="ghost" onClick={close}>
              {t("Close")}
            </Button>
          </div>

          {result.video_url ? (
            <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-black">
              <MediaPlayer
                className="mx-auto max-h-[300px] w-full"
                aspectRatio="16/9"
                title={caseName ?? `#${result.case_id}`}
                src={result.video_url}
              >
                <MediaProvider />
                <DefaultVideoLayout icons={defaultLayoutIcons} />
              </MediaPlayer>
            </div>
          ) : (
            <div className="rounded-xl bg-[var(--panel2)] px-3 py-6 text-center text-sm text-ink-500">
              {t("no video recorded")}
              {diag.length > 0 ? t(" — see the step timeline below") : ""}
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <div>
              <span className="text-ink-500">{t("Judge")}: </span>
              {result.judge_reason ?? result.error ?? "—"}
            </div>
            <div>
              <span className="text-ink-500">{t("Final answer")}: </span>
              {result.final_answer || "—"}
            </div>
          </div>

          {diag.length > 0 ? (
            <>
              <div className="mb-2 mt-5 flex items-center gap-2 text-sm font-medium text-ink-900">
                {t("Step timeline")}
                <span className="rounded-full bg-[var(--panel2)] px-1.5 py-0.5 text-[11px] font-normal text-ink-500">
                  {diag.length}
                </span>
                <span className="text-xs font-normal text-ink-500">{t("thought → action → result")}</span>
              </div>
              <div>
                {diag.map((step) => (
                  <div
                    key={step.i}
                    className="grid grid-cols-[26px_1fr_auto] gap-3 border-b border-[var(--line)] py-2.5 last:border-0"
                  >
                    <div
                      className={
                        "grid h-[22px] w-[22px] place-items-center rounded-full text-[11px] font-bold text-[var(--on-brand)] " +
                        (step.error ? "bg-[var(--bad-fg)]" : "bg-brand-600")
                      }
                    >
                      {step.i}
                    </div>
                    <div className="min-w-0">
                      <div className="mb-1">
                        <span className="rounded bg-brand-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-brand-700">
                          {step.action}
                        </span>
                      </div>
                      {step.thought && (
                        <div className="text-[13px] leading-relaxed text-ink-700">
                          <span className="mr-1.5 text-ink-500">💭</span>
                          {step.thought}
                        </div>
                      )}
                      {step.result && <div className="mt-1 text-xs text-[var(--ok-fg)]">✓ {step.result}</div>}
                      {step.error && <div className="mt-1 text-xs text-[var(--bad-fg)]">✗ {step.error}</div>}
                    </div>
                    {step.screenshot ? (
                      <button
                        onClick={() => setShotIdx(shots.findIndex((s) => s.i === step.i))}
                        title={t("click to enlarge")}
                        className="block cursor-zoom-in"
                      >
                        <img
                          src={step.screenshot}
                          alt={`step ${step.i}`}
                          className="h-[70px] w-[120px] rounded-md border border-[var(--line)] object-cover"
                        />
                      </button>
                    ) : (
                      <div className="w-[120px]" />
                    )}
                  </div>
                ))}
              </div>

              <div className="mt-4 overflow-hidden rounded-lg border border-[var(--line)]">
                <button
                  onClick={() => setRawOpen((o) => !o)}
                  className="flex w-full items-center gap-2 bg-[var(--panel2)] px-3 py-2 text-left text-xs font-semibold text-ink-900"
                >
                  <span className="text-ink-500">{rawOpen ? "▾" : "▸"}</span>
                  {t("Raw agent log")}
                  <span className="font-normal text-ink-500">({diag.length})</span>
                </button>
                {rawOpen && (
                  <pre className="whitespace-pre-wrap px-3 py-2 font-mono text-[11.5px] leading-relaxed text-ink-700">
                    {diag
                      .map(
                        (s) =>
                          `#${s.i} ${s.action}\n  💭 ${s.thought}\n  ${s.error ? "✗ " + s.error : "✓ " + (s.result || "")}`,
                      )
                      .join("\n")}
                  </pre>
                )}
              </div>
            </>
          ) : (
            <div className="mt-5 rounded-lg bg-[var(--panel2)] px-3 py-6 text-center text-xs text-ink-500">
              {t("No step diagnostics captured for this run.")}
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-4 text-xs">
            {result.video_url && (
              <a
                href={result.video_url}
                download={`run-${result.run_id}-case-${result.case_id}.mp4`}
                className="inline-block text-brand-700 underline"
              >
                {t("download video (mp4)")}
              </a>
            )}
            {result.trace_url && (
              <a
                href={result.trace_url}
                target="_blank"
                rel="noreferrer"
                className="inline-block text-brand-700 underline"
              >
                {t("download operation trace (history.json)")}
              </a>
            )}
          </div>
          {shotIdx !== null && (
            <ShotViewer shots={shots} index={shotIdx} onIndex={setShotIdx} onClose={() => setShotIdx(null)} />
          )}
        </Card>
      )}
    </Modal>
  );
}
