import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, relTime, type FeedbackItem } from "../lib/api";
import { Badge, Button, Select } from "./ui";
import { useToast } from "./toast";

const CATEGORY_BADGE: Record<string, string> = {
  bug: "failed",
  feature: "running",
  question: "error",
  other: "pending",
};
const SEVERITY_BADGE: Record<string, string> = {
  critical: "failed",
  high: "error",
  medium: "pending",
  low: "pending",
};

export function FeedbackTab({ pid }: { pid: number }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [category, setCategory] = useState("");
  const [promoting, setPromoting] = useState<number | null>(null);

  const load = () =>
    api
      .listProjectFeedback(pid, { category: category || undefined })
      .then(setItems)
      .catch((e) => toast("error", String(e)));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid, category]);

  const promote = async (f: FeedbackItem) => {
    setPromoting(f.id);
    try {
      const issue = await api.promoteFeedback(f.id);
      toast("success", t("Promoted to issue #{{id}}", { id: issue.id }));
      load();
    } catch (e) {
      toast("error", String(e));
    } finally {
      setPromoting(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-xs text-ink-500">{t("Category")}</span>
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-40">
          <option value="">{t("All")}</option>
          <option value="bug">bug</option>
          <option value="feature">feature</option>
          <option value="question">question</option>
          <option value="other">other</option>
        </Select>
      </div>

      <div className="rounded-lg border border-[var(--line)]">
        <table className="w-full text-sm">
          <thead className="border-b border-[var(--line)] text-left text-xs text-ink-500">
            <tr>
              <th className="px-4 py-2">{t("Problem")}</th>
              <th className="px-4 py-2">{t("Category")}</th>
              <th className="px-4 py-2">{t("Severity")}</th>
              <th className="px-4 py-2">{t("From")}</th>
              <th className="px-4 py-2">{t("When")}</th>
              <th className="px-4 py-2 text-right">{t("Issue")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((f) => (
              <tr key={f.id} className="border-b border-[var(--line)] align-top last:border-0">
                <td className="max-w-[26rem] px-4 py-2">
                  <div className="font-medium text-ink-900">{f.title ?? f.content.slice(0, 40)}</div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-ink-500">{f.content}</div>
                  {f.answer && (
                    <div className="mt-1 line-clamp-2 text-xs text-brand-700">↳ {f.answer}</div>
                  )}
                </td>
                <td className="px-4 py-2">
                  <Badge status={CATEGORY_BADGE[f.category] ?? "pending"}>{f.category}</Badge>
                </td>
                <td className="px-4 py-2">
                  <Badge status={SEVERITY_BADGE[f.severity] ?? "pending"}>{f.severity}</Badge>
                </td>
                <td className="px-4 py-2 text-xs text-ink-500">{f.sender_name ?? f.sender_id ?? "—"}</td>
                <td className="whitespace-nowrap px-4 py-2 text-xs text-ink-500">
                  {relTime(f.created_at)}
                </td>
                <td className="px-4 py-2 text-right">
                  {f.issue_id != null ? (
                    <span className="text-xs text-ink-500">#{f.issue_id}</span>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={promoting === f.id}
                      onClick={() => promote(f)}
                    >
                      {promoting === f.id ? t("…") : t("Promote to issue")}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-sm text-ink-500">
                  {t("No feedback yet.")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
