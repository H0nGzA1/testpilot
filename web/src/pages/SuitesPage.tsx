import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { api, type Cadence, type Environment, type Member, type Suite, type TestCase } from "../lib/api";
import { Badge, Button, Card, Field, Input, Select, Textarea } from "../components/ui";
import { CADENCE_LABELS, label } from "../lib/labels";
import { CasePicker } from "../components/CasePicker";
import { useToast } from "../components/toast";

const CADENCES: Cadence[] = ["none", "daily", "weekly", "biweekly", "monthly"];

const emptyDraft = (): Partial<Suite> => ({
  name: "",
  description: "",
  selection_mode: "cases",
  case_ids: [],
  tag_filter: [],
  owner_user_id: null,
  runner_user_id: null,
  cadence: "none",
});

function relDue(due: string | null): string {
  if (!due) return "—";
  const d = new Date(due).getTime();
  const days = Math.round((d - Date.now()) / 86400000);
  if (days < 0) return `逾期 ${-days} 天`;
  if (days === 0) return "今日到期";
  return `${days} 天后`;
}

export function SuitesPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const toast = useToast();
  const navigate = useNavigate();
  const pid = Number(useParams().pid);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [cases, setCases] = useState<TestCase[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [envs, setEnvs] = useState<Environment[]>([]);
  const [draft, setDraft] = useState<Partial<Suite> | null>(null);

  const load = () => api.listSuites(pid).then(setSuites).catch((e) => toast("error", String(e)));
  useEffect(() => {
    load();
    api.listCases(pid).then(setCases).catch(() => {});
    api.listMembers(pid).then(setMembers).catch(() => {});
    api.listEnvironments(pid).then(setEnvs).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  const memberOpts = useMemo(
    () => members.map((m) => ({ id: m.user_id, label: m.name || m.email })),
    [members],
  );

  const set = <K extends keyof Suite>(k: K, v: Suite[K]) => setDraft((d) => ({ ...d, [k]: v }));

  const save = async () => {
    if (!draft?.name?.trim()) return toast("error", t("Name is required"));
    const body = {
      name: draft.name!.trim(),
      description: draft.description ?? "",
      selection_mode: "cases" as const,
      case_ids: draft.case_ids ?? [],
      owner_user_id: draft.owner_user_id ?? null,
      runner_user_id: draft.runner_user_id ?? null,
      cadence: (draft.cadence ?? "none") as Cadence,
      environment_id: draft.environment_id ?? null,
    };
    try {
      if (draft.id) await api.updateSuite(draft.id, body);
      else await api.createSuite(pid, body);
      setDraft(null);
      load();
      toast("success", t("Saved"));
    } catch (e) {
      toast("error", String(e));
    }
  };

  const run = async (s: Suite) => {
    try {
      const r = await api.runSuite(s.id);
      toast("success", t("Run started"));
      navigate(`/projects/${pid}/runs/${r.id}`);
    } catch (e) {
      toast("error", String(e));
    }
  };

  const remove = async (s: Suite) => {
    try {
      await api.deleteSuite(s.id);
      load();
    } catch (e) {
      toast("error", String(e));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink-900">{t("Suites")}</h1>
          <p className="mt-1 text-sm text-ink-500">
            {t("Owned, assigned test suites with reminders. Anyone can run; each run records who did.")}
          </p>
        </div>
        <Button onClick={() => setDraft(emptyDraft())}>{t("New suite")}</Button>
      </div>

      <Card>
        <table className="w-full text-sm">
          <thead className="border-b border-[var(--line)] text-left text-xs text-ink-500">
            <tr>
              <th className="px-4 py-2">{t("Name")}</th>
              <th className="px-4 py-2">{t("Owner")}</th>
              <th className="px-4 py-2">{t("Runner")}</th>
              <th className="px-4 py-2">{t("Cadence")}</th>
              <th className="px-4 py-2">{t("Next due")}</th>
              <th className="px-4 py-2">{t("Last")}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {suites.map((s) => (
              <tr key={s.id} className="border-b border-[var(--line)] last:border-0 hover:bg-brand-50/40">
                <td className="px-4 py-2 font-medium text-ink-900">
                  {s.name}
                  <span className="ml-2 text-xs text-ink-400">{s.case_ids.length} 用例</span>
                </td>
                <td className="px-4 py-2 text-ink-700">{s.owner_label ?? "—"}</td>
                <td className="px-4 py-2 text-ink-700">{s.runner_label ?? "—"}</td>
                <td className="px-4 py-2 text-ink-700">{label(CADENCE_LABELS, s.cadence, lang)}</td>
                <td className="px-4 py-2 text-ink-700">{s.cadence === "none" ? "—" : relDue(s.due_at)}</td>
                <td className="px-4 py-2">
                  {s.last_status ? <Badge status={s.last_status}>{s.last_status}</Badge> : <span className="text-ink-400">—</span>}
                </td>
                <td className="px-4 py-2">
                  <div className="flex justify-end gap-1">
                    <Button size="sm" onClick={() => run(s)}>{t("Run")}</Button>
                    <Button size="sm" variant="outline" onClick={() => setDraft({ ...s })}>{t("Edit")}</Button>
                    <Button size="sm" variant="danger" onClick={() => remove(s)}>{t("Delete")}</Button>
                  </div>
                </td>
              </tr>
            ))}
            {suites.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-ink-500">
                  {t("No suites yet. A suite is a saved set of cases with an owner and a schedule — use it for recurring regression runs.")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      {draft && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={() => setDraft(null)}>
          <div
            className="tp-pop h-full w-[34rem] max-w-full overflow-y-auto bg-[var(--panel)] p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-ink-900">
                {draft.id ? t("Edit suite") : t("New suite")}
              </h2>
              <button className="text-sm text-ink-500 hover:text-ink-900" onClick={() => setDraft(null)}>
                {t("Close")}
              </button>
            </div>
            <div className="space-y-4">
              <Field label={t("Name")}>
                <Input value={draft.name ?? ""} onChange={(e) => set("name", e.target.value)} placeholder="回归套件" />
              </Field>
              <Field label={t("Description")}>
                <Textarea rows={2} value={draft.description ?? ""} onChange={(e) => set("description", e.target.value)} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("Owner")}>
                  <Select
                    value={draft.owner_user_id != null ? String(draft.owner_user_id) : ""}
                    onValueChange={(v) => set("owner_user_id", v ? Number(v) : null)}
                  >
                    <option value="">{t("— none —")}</option>
                    {memberOpts.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </Select>
                </Field>
                <Field label={t("Default runner")}>
                  <Select
                    value={draft.runner_user_id != null ? String(draft.runner_user_id) : ""}
                    onValueChange={(v) => set("runner_user_id", v ? Number(v) : null)}
                  >
                    <option value="">{t("— none —")}</option>
                    {memberOpts.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </Select>
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("Cadence (drives reminders; does not auto-run)")}>
                  <Select value={draft.cadence ?? "none"} onValueChange={(v) => set("cadence", v as Cadence)}>
                    {CADENCES.map((c) => <option key={c} value={c}>{label(CADENCE_LABELS, c, lang)}</option>)}
                  </Select>
                </Field>
                <Field label={t("Environment")}>
                  <Select
                    value={draft.environment_id != null ? String(draft.environment_id) : ""}
                    onValueChange={(v) => set("environment_id", v ? Number(v) : null)}
                  >
                    <option value="">{t("— project default —")}</option>
                    {envs.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </Select>
                </Field>
              </div>
              <Field label={t("Cases in this suite")}>
                {cases.length === 0 ? (
                  <div className="rounded-lg border border-[var(--line)] px-2 py-3 text-xs text-ink-400">
                    {t("No cases in this project yet.")}
                  </div>
                ) : (
                  <CasePicker
                    cases={cases}
                    selected={draft.case_ids ?? []}
                    onChange={(ids) => set("case_ids", ids)}
                  />
                )}
              </Field>
              <div className="flex gap-2 pt-2">
                <Button onClick={save}>{t("Save")}</Button>
                <Button variant="outline" onClick={() => setDraft(null)}>{t("Cancel")}</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
