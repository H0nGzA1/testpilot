import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api, relTime, type Issue, type IssueComment, type Severity } from "../lib/api";
import { Badge, Button, Card, Field, Input, Select, Textarea } from "./ui";
import { Modal } from "./Modal";
import { useToast } from "./toast";

const STATUSES = ["open", "in_progress", "fixed", "verified", "closed"] as const;
const SEVERITIES: Severity[] = ["low", "medium", "high", "critical"];

export function IssueDrawer({
  issueId,
  pid,
  onClose,
  onChanged,
}: {
  issueId: number;
  pid: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [issue, setIssue] = useState<Issue | null>(null);
  const [comments, setComments] = useState<IssueComment[]>([]);
  const [comment, setComment] = useState("");

  const load = () =>
    api.getIssue(issueId).then((i) => {
      setIssue(i);
      setComments(i.comments ?? []);
    });
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [issueId]);

  if (!issue) return null;

  const patch = async (b: Partial<Issue>) => {
    const next = await api.updateIssue(issueId, b);
    setIssue({ ...next, comments });
    onChanged();
  };
  const save = async () => {
    try {
      await patch({
        title: issue.title,
        description: issue.description,
        severity: issue.severity,
        assignee: issue.assignee,
        labels: issue.labels,
      });
      toast("success", t("Issue saved"));
    } catch (e) {
      toast("error", String(e));
    }
  };
  const rerunCase = async () => {
    if (!issue.case_id) return;
    try {
      const run = await api.createRun(pid, { name: `verify issue #${issue.id}`, case_ids: [issue.case_id] });
      toast("success", t("Re-running the linked case"));
      navigate(`/projects/${pid}/runs/${run.id}`);
    } catch (e) {
      toast("error", String(e));
    }
  };
  const addComment = async () => {
    if (!comment.trim()) return;
    await api.addComment(issueId, { body: comment });
    setComment("");
    load();
  };

  return (
    <Modal onClose={onClose} className="max-w-xl">
      {(close) => (
      <Card className="max-h-[85vh] overflow-auto p-0 shadow-xl">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="font-medium text-ink-900">{t("Issue #")}{issue.id}</span>
            <Badge status={issue.status === "closed" || issue.status === "verified" ? "passed" : issue.status === "open" ? "failed" : "running"}>
              {issue.status}
            </Badge>
            {issue.gitlab_url && (
              <a
                href={issue.gitlab_url}
                target="_blank"
                rel="noreferrer"
                className="rounded-full bg-[var(--panel2)] px-2 py-0.5 text-[11px] text-brand-700 hover:underline"
              >
                {t("GitLab !{{iid}}", { iid: issue.gitlab_iid })}
              </a>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={close}>
            {t("Close")}
          </Button>
        </div>

        <div className="space-y-4 p-5">
          <Field label={t("Title")}>
            <Input value={issue.title} onChange={(e) => setIssue({ ...issue, title: e.target.value })} />
          </Field>
          <Field label={t("Description")}>
            <Textarea rows={4} value={issue.description} onChange={(e) => setIssue({ ...issue, description: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("Status")}>
              <Select
                value={issue.status}
                onChange={(e) => patch({ status: e.target.value as Issue["status"] })}
              >
                {STATUSES.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("Severity")}>
              <Select
                value={issue.severity}
                onChange={(e) => setIssue({ ...issue, severity: e.target.value as Severity })}
              >
                {SEVERITIES.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("Assignee")}>
              <Input value={issue.assignee ?? ""} onChange={(e) => setIssue({ ...issue, assignee: e.target.value })} placeholder={t("unassigned")} />
            </Field>
            <Field label={t("Labels (comma-separated)")}>
              <Input
                value={(issue.labels ?? []).join(", ")}
                onChange={(e) => setIssue({ ...issue, labels: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })}
              />
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
            {issue.case_id && <span>case #{issue.case_id}</span>}
            {issue.run_id && (
              <a href={`/projects/${pid}/runs/${issue.run_id}`} className="text-brand-700 hover:underline">
                run #{issue.run_id}
              </a>
            )}
            <span className="ml-auto">updated {relTime(issue.updated_at)}</span>
          </div>

          <div className="flex gap-2">
            <Button onClick={save}>{t("Save")}</Button>
            {issue.case_id && (
              <Button variant="outline" onClick={rerunCase}>
                {t("Re-run case to verify")}
              </Button>
            )}
          </div>

          <div className="border-t border-[var(--line)] pt-4">
            <div className="mb-2 text-sm font-medium text-ink-900">{t("Comments")} ({comments.length})</div>
            <div className="space-y-2">
              {comments.map((c) => (
                <div key={c.id} className="rounded-lg border border-[var(--line)] px-3 py-2 text-sm">
                  <div className="text-ink-700">{c.body}</div>
                  <div className="mt-1 text-[11px] text-ink-500">{c.author ?? "anon"} · {relTime(c.created_at)}</div>
                </div>
              ))}
            </div>
            <div className="mt-2 flex gap-2">
              <Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t("Add a comment…")} />
              <Button variant="outline" onClick={addComment}>
                {t("Add")}
              </Button>
            </div>
          </div>
        </div>
      </Card>
      )}
    </Modal>
  );
}
