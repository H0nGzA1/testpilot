import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, type GitLabConfig } from "../lib/api";
import { Button, Card, Field, Input, Select } from "./ui";
import { useToast } from "./toast";

type GLProject = { id: number; path: string; name: string | null };

export function GitLabSection({ pid }: { pid: number }) {
  const toast = useToast();
  const { t } = useTranslation();
  const [cfg, setCfg] = useState<GitLabConfig | null>(null);
  const [project, setProject] = useState("");
  const [saving, setSaving] = useState(false);
  const [projects, setProjects] = useState<GLProject[] | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [manual, setManual] = useState(false);

  const load = () =>
    api
      .getGitlabConfig(pid)
      .then((c) => {
        setCfg(c);
        setProject(c.gitlab_project ?? "");
        if (c.has_token) loadProjects();
      })
      .catch((e) => toast("error", String(e)));

  const loadProjects = () => {
    setLoadingList(true);
    api
      .listGitlabProjects(pid)
      .then(setProjects)
      .catch((e) => toast("error", String(e)))
      .finally(() => setLoadingList(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  const save = async () => {
    setSaving(true);
    try {
      await api.setGitlabConfig(pid, { gitlab_project: project.trim() });
      toast("success", t("GitLab settings saved"));
      load();
    } catch (e) {
      toast("error", String(e));
    } finally {
      setSaving(false);
    }
  };

  const useDropdown = cfg?.has_token && projects !== null && !manual;
  const options =
    useDropdown && project && !projects!.some((p) => p.path === project)
      ? [{ id: -1, path: project, name: project }, ...projects!]
      : (projects ?? []);

  return (
    <Card className="space-y-4 p-4">
      <div>
        <div className="text-sm font-medium text-ink-900">{t("GitLab sync")}</div>
        <div className="text-xs text-ink-500">
          {t("Two-way sync issues with a GitLab project. New issues auto-push; status, labels and comments stay in sync.")}
        </div>
      </div>

      {cfg && !cfg.sync_enabled && (
        <div className="rounded-lg bg-[var(--warn-bg)] px-3 py-2 text-xs text-[var(--warn-fg)]">
          {t("Sync worker is not running (REDIS_URL unset). You can save the mapping now; syncing starts once the Celery worker/beat are up.")}
        </div>
      )}

      {cfg && !cfg.has_token ? (
        <div className="rounded-lg bg-[var(--warn-bg)] px-3 py-2 text-xs text-[var(--warn-fg)]">
          {t("No GitLab token configured yet.")}{" "}
          <Link to="/admin/settings" className="underline">{t("Set it in System settings.")}</Link>
        </div>
      ) : (
        <div className="max-w-md">
          <Field label={t("GitLab project")}>
            {useDropdown ? (
              <div className="flex items-center gap-2">
                <Select value={project} onChange={(e) => setProject(e.target.value)}>
                  <option value="">{t("— none (keep issues local) —")}</option>
                  {options.map((p) => (
                    <option key={p.id} value={p.path}>{p.path}</option>
                  ))}
                </Select>
                <button type="button" onClick={loadProjects} title={t("Refresh")}
                  className="shrink-0 rounded-lg border border-[var(--line)] px-2 py-1.5 text-xs text-ink-500 hover:text-ink-900">
                  {loadingList ? "…" : "↻"}
                </button>
              </div>
            ) : (
              <Input value={project} onChange={(e) => setProject(e.target.value)} placeholder="agent/testpilot" />
            )}
            <button type="button" onClick={() => setManual((m) => !m)}
              className="mt-1 text-[11px] text-brand-700 hover:underline">
              {manual ? t("Pick from list") : t("Enter path manually")}
            </button>
          </Field>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={saving || !cfg?.has_token}>
          {saving ? t("Saving…") : t("Save GitLab settings")}
        </Button>
        <span className="text-xs text-ink-500">
          {cfg?.gitlab_project
            ? t("Linked to {{p}}", { p: cfg.gitlab_project })
            : t("Not linked — leave the project blank to keep issues local only.")}
        </span>
      </div>
      <p className="text-xs text-ink-500">{t("The GitLab token is managed by an admin under System settings.")}</p>
    </Card>
  );
}
