import { Check, ChevronRight, Circle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ProjectStats } from "../lib/api";
import { Card } from "./ui";

/** First-run setup checklist. Every item is DERIVED from live project state — there is
 *  no stored "onboarding done" flag, so it can never disagree with reality, and the
 *  whole card disappears on its own once the project is set up. */
export function SetupChecklist({ pid, stats }: { pid: number; stats: ProjectStats }) {
  const { t } = useTranslation();
  const lastGreen = stats.run_count > 0 && stats.last_pass_rate === 1;

  const items = [
    {
      done: !!stats.base_url,
      title: t("Set the base URL"),
      sub: t("Where the agent starts each case."),
      to: `/projects/${pid}/settings`,
      cta: t("Settings"),
    },
    {
      done: stats.has_healthy_credential,
      title: t("Add a working account"),
      sub: stats.has_credential
        ? t("A credential exists but its session is stale — re-capture it.")
        : t("Capture a login session so the agent can reach pages behind sign-in."),
      to: `/projects/${pid}/settings`,
      cta: t("Credentials"),
    },
    {
      done: stats.case_count > 0,
      title: t("Write your first test case"),
      sub: t("A case is a natural-language task plus one line saying what counts as a pass."),
      to: `/projects/${pid}/cases`,
      cta: t("Test Cases"),
    },
    {
      done: stats.run_count > 0,
      title: t("Run it once"),
      sub: t("Start with a single case. First run takes 30–90s — a real browser is launched and recorded."),
      to: `/projects/${pid}/cases`,
      cta: t("Run a case"),
    },
    {
      done: lastGreen || stats.issue_count > 0,
      title: t("Act on the result"),
      sub: t("Green everywhere, or turn a failure into an issue from the report."),
      to: `/projects/${pid}/runs`,
      cta: t("Runs"),
    },
  ];

  const done = items.filter((i) => i.done).length;
  if (done === items.length) return null;

  const next = items.findIndex((i) => !i.done);

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-ink-900">{t("Get this project running")}</div>
          <div className="mt-0.5 text-xs text-ink-500">
            {t("This card disappears once you're set up.")}
          </div>
        </div>
        <div className="text-xs tabular-nums text-ink-500">
          {done}/{items.length}
        </div>
      </div>

      <ol className="space-y-1">
        {items.map((it, i) => (
          <li key={it.title}>
            <Link
              to={it.to}
              className="flex items-start gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-brand-50"
            >
              {it.done ? (
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
              ) : (
                <Circle className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" />
              )}
              <div className="min-w-0 flex-1">
                <div
                  className={
                    it.done
                      ? "text-sm text-ink-400 line-through"
                      : "text-sm font-medium text-ink-900"
                  }
                >
                  {it.title}
                </div>
                {i === next && <div className="mt-0.5 text-xs text-ink-500">{it.sub}</div>}
              </div>
              {i === next && (
                <span className="flex shrink-0 items-center gap-0.5 text-xs font-medium text-brand-700">
                  {it.cta}
                  <ChevronRight className="h-3.5 w-3.5" />
                </span>
              )}
            </Link>
          </li>
        ))}
      </ol>
    </Card>
  );
}
