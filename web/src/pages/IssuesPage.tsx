import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { api, relTime, type Issue } from "../lib/api";
import { Button, Select } from "../components/ui";
import { IssueDrawer } from "../components/IssueDrawer";
import { FeedbackTab } from "../components/FeedbackTab";
import { useToast } from "../components/toast";

const COLUMNS: { key: Issue["status"]; label: string }[] = [
  { key: "open", label: "Open" },
  { key: "in_progress", label: "In progress" },
  { key: "fixed", label: "Fixed" },
  { key: "verified", label: "Verified" },
  { key: "closed", label: "Closed" },
];

const SEV_COLOR: Record<string, string> = {
  low: "bg-[var(--panel2)] text-ink-500",
  medium: "bg-[var(--warn-bg)] text-[var(--warn-fg)]",
  high: "bg-[var(--bad-bg)] text-[var(--bad-fg)]",
  critical: "bg-[var(--bad-bg)] text-[var(--bad-fg)] font-semibold",
};

export function IssuesPage() {
  const pid = Number(useParams().pid);
  const toast = useToast();
  const { t } = useTranslation();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [tab, setTab] = useState<"issues" | "feedback">("issues");

  const load = () => api.listIssues(pid).then(setIssues).catch((e) => toast("error", String(e)));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  const newIssue = async () => {
    try {
      const i = await api.createIssue(pid, { title: "Untitled issue" });
      await load();
      setSelected(i.id);
    } catch (e) {
      toast("error", String(e));
    }
  };

  const move = async (i: Issue, status: Issue["status"]) => {
    await api.updateIssue(i.id, { status });
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink-900">{t("Issues")}</h1>
          <p className="mt-1 text-sm text-ink-500">{t("Bugs from failed tests — track, fix, and re-run to verify.")}</p>
        </div>
        {tab === "issues" && <Button onClick={newIssue}>{t("+ New issue")}</Button>}
      </div>

      <div className="inline-flex rounded-lg border border-[var(--line)] bg-[var(--panel2)] p-0.5">
        {(["issues", "feedback"] as const).map((k) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={
              "rounded-md px-3 py-1 text-xs font-medium transition-colors " +
              (tab === k
                ? "bg-brand-600 text-[var(--on-brand)] shadow-sm"
                : "text-ink-700 hover:text-ink-900")
            }
          >
            {k === "issues" ? t("Issues") : t("Feedback")}
          </button>
        ))}
      </div>

      {tab === "feedback" && <FeedbackTab pid={pid} />}

      {tab === "issues" && (
      <div className="flex gap-3 overflow-x-auto pb-2">
        {COLUMNS.map((col) => {
          const items = issues.filter((i) => i.status === col.key);
          return (
            <div key={col.key} className="w-64 shrink-0">
              <div className="mb-2 flex items-center gap-2 px-1 text-sm font-medium text-ink-700">
                {t(col.label)}
                <span className="rounded-full bg-[var(--panel2)] px-1.5 text-xs text-ink-500">{items.length}</span>
              </div>
              <div className="space-y-2">
                {items.map((i) => (
                  // a div (not <button>) so the status Select's button trigger can nest
                  // validly; keyboard-activatable to keep it accessible.
                  <div
                    key={i.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelected(i.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelected(i.id);
                      }
                    }}
                    className="block w-full cursor-pointer rounded-lg border border-[var(--line)] bg-[var(--panel)] p-3 text-left transition-colors hover:border-brand-100"
                  >
                    <div className="flex items-center gap-2">
                      <span className={"rounded px-1.5 py-0.5 text-[10px] font-medium " + (SEV_COLOR[i.severity] ?? "")}>
                        {i.severity}
                      </span>
                      <span className="text-[11px] text-ink-500">#{i.id}</span>
                      {i.case_id && <span className="ml-auto text-[11px] text-ink-500">case #{i.case_id}</span>}
                    </div>
                    <div className="mt-1.5 line-clamp-2 text-sm text-ink-900">{i.title}</div>
                    <div className="mt-2 flex items-center justify-between">
                      <span
                        role="presentation"
                        onClick={(e) => e.stopPropagation()}
                        onPointerDown={(e) => e.stopPropagation()}
                      >
                        <Select
                          variant="bare"
                          value={i.status}
                          onValueChange={(v) => move(i, v as Issue["status"])}
                          className="border border-[var(--line)]"
                        >
                          {COLUMNS.map((c) => (
                            <option key={c.key} value={c.key}>
                              {t(c.label)}
                            </option>
                          ))}
                        </Select>
                      </span>
                      <span className="text-[11px] text-ink-500">{relTime(i.updated_at)}</span>
                    </div>
                  </div>
                ))}
                {items.length === 0 && (
                  <div className="rounded-lg border border-dashed border-[var(--line)] py-6 text-center text-xs text-ink-500">
                    {t("empty")}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      )}

      {selected != null && (
        <IssueDrawer
          issueId={selected}
          pid={pid}
          onClose={() => setSelected(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}
