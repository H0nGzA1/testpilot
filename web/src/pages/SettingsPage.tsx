import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { api, type Credential, type Environment } from "../lib/api";
import { getTheme, setTheme, type ThemeMode } from "../lib/theme";
import { Badge, Button, Card, Field, Input } from "../components/ui";
import { CredentialsSection } from "../components/CredentialsSection";
import { GitLabSection } from "../components/GitLabSection";
import { useToast } from "../components/toast";
import { useAuth } from "../lib/auth";

const THEME_MODES: ThemeMode[] = ["system", "light", "dark"];
const THEME_LABEL: Record<ThemeMode, string> = { system: "System", light: "Light", dark: "Dark" };

export function SettingsPage() {
  const pid = Number(useParams().pid);
  const toast = useToast();
  const { gitlabEnabled, feishuEnabled } = useAuth();
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [timeout, setTimeoutS] = useState("");
  const [maxSteps, setMaxSteps] = useState("");
  const [concurrency, setConcurrency] = useState("");
  const [feishuChatId, setFeishuChatId] = useState("");
  const [bitableUrl, setBitableUrl] = useState("");
  const [bitableBound, setBitableBound] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingRun, setSavingRun] = useState(false);
  const [savingFeishu, setSavingFeishu] = useState(false);
  const [theme, setThemeState] = useState<ThemeMode>(getTheme);
  const [roles, setRoles] = useState<string[]>([]);
  const [newRole, setNewRole] = useState("");
  const [envs, setEnvs] = useState<Environment[]>([]);
  const [newEnvName, setNewEnvName] = useState("");
  const [newEnvUrl, setNewEnvUrl] = useState("");
  const [editEnv, setEditEnv] = useState<{ id: number; name: string; base_url: string } | null>(null);
  const [creds, setCreds] = useState<Credential[]>([]);

  const loadCreds = () => api.listCredentials(pid).then(setCreds).catch(() => {});
  useEffect(() => {
    api.getRoles(pid).then((r) => setRoles(r.roles)).catch(() => {});
    api.listEnvironments(pid).then(setEnvs).catch(() => {});
    loadCreds();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  // accounts bound per role / per environment — surfaced so a role with 0 accounts is
  // caught here, not at run time ("no available account for role X")
  const roleAccounts = (r: string) => creds.filter((c) => c.role === r).length;
  const envAccounts = (id: number) => creds.filter((c) => c.environment_id === id).length;

  const loadEnvs = () => api.listEnvironments(pid).then(setEnvs).catch(() => {});
  const saveEnvEdit = async () => {
    if (!editEnv || !editEnv.name.trim()) return;
    try {
      await api.updateEnvironment(editEnv.id, {
        name: editEnv.name.trim(),
        base_url: editEnv.base_url.trim() || null,
      });
      setEditEnv(null);
      loadEnvs();
    } catch (e) {
      toast("error", String(e));
    }
  };
  const addEnv = async () => {
    if (!newEnvName.trim()) return;
    try {
      await api.createEnvironment(pid, {
        name: newEnvName.trim(),
        base_url: newEnvUrl.trim() || undefined,
        is_default: envs.length === 0,
      });
      setNewEnvName("");
      setNewEnvUrl("");
      loadEnvs();
    } catch (e) {
      toast("error", String(e));
    }
  };

  const saveRoles = async (next: string[]) => {
    try {
      const r = await api.setRoles(pid, next);
      setRoles(r.roles);
    } catch (e) {
      toast("error", String(e));
    }
  };
  const addRole = () => {
    const v = newRole.trim();
    if (!v || roles.includes(v)) return;
    setNewRole("");
    saveRoles([...roles, v]);
  };

  useEffect(() => {
    api.listProjects().then((ps) => {
      const p = ps.find((x) => x.id === pid) ?? null;
      setName(p?.name ?? "");
      setBaseUrl(p?.base_url ?? "");
      setTimeoutS(p?.case_timeout_s != null ? String(p.case_timeout_s) : "");
      setMaxSteps(p?.case_max_steps != null ? String(p.case_max_steps) : "");
      setConcurrency(p?.run_concurrency != null ? String(p.run_concurrency) : "");
      setFeishuChatId(p?.feishu_chat_id ?? "");
      setBitableBound(p?.feishu_bitable_bound ?? false);
    });
  }, [pid]);

  const save = async () => {
    setSaving(true);
    try {
      await api.updateProject(pid, { name, base_url: baseUrl });
      toast("success", t("Settings saved"));
    } catch (e) {
      toast("error", String(e));
    } finally {
      setSaving(false);
    }
  };

  const saveFeishu = async () => {
    setSavingFeishu(true);
    try {
      const body: { feishu_chat_id: string; feishu_bitable_url?: string } = {
        feishu_chat_id: feishuChatId.trim(),
      };
      if (bitableUrl.trim()) body.feishu_bitable_url = bitableUrl.trim();
      const p = await api.updateProject(pid, body);
      setBitableBound(p.feishu_bitable_bound ?? false);
      setBitableUrl("");
      toast("success", t("Settings saved"));
    } catch (e) {
      toast("error", String(e));
    } finally {
      setSavingFeishu(false);
    }
  };

  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  const saveRun = async () => {
    setSavingRun(true);
    try {
      await api.updateProject(pid, {
        case_timeout_s: num(timeout),
        case_max_steps: num(maxSteps),
        run_concurrency: num(concurrency),
      });
      toast("success", t("Settings saved"));
    } catch (e) {
      toast("error", String(e));
    } finally {
      setSavingRun(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">{t("Settings")}</h1>
        <p className="mt-1 text-sm text-ink-500">{t("Project configuration.")}</p>
      </div>

      <div className="max-w-2xl space-y-6">
        <Card className="space-y-3 p-4">
          <div>
            <div className="text-sm font-medium text-ink-900">{t("Appearance")}</div>
            <div className="mt-0.5 text-xs text-ink-500">{t("Follow system / browser by default.")}</div>
          </div>
          <div className="inline-flex rounded-lg border border-[var(--line)] bg-[var(--panel2)] p-0.5">
            {THEME_MODES.map((m) => (
              <button
                key={m}
                onClick={() => {
                  setTheme(m);
                  setThemeState(m);
                }}
                className={
                  "rounded-md px-3 py-1 text-xs font-medium transition-colors " +
                  (theme === m ? "bg-brand-600 text-[var(--on-brand)] shadow-sm" : "text-ink-700 hover:text-ink-900")
                }
              >
                {t(THEME_LABEL[m])}
              </button>
            ))}
          </div>
        </Card>

        <Card className="space-y-4 p-4">
          <Field label={t("Project name")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label={t("Base URL")}>
            <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://your-app.example.com" />
          </Field>
          <Button onClick={save} disabled={saving}>
            {saving ? t("Saving…") : t("Save changes")}
          </Button>
        </Card>

        <Card className="space-y-4 p-4">
          <div>
            <div className="text-sm font-medium text-ink-900">{t("Run defaults")}</div>
            <div className="mt-0.5 text-xs text-ink-500">
              {t("Applied to every case in this project. Leave blank to use the system default.")}
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label={t("Timeout per case (s)")}>
              <Input
                type="number"
                min={15}
                max={600}
                value={timeout}
                onChange={(e) => setTimeoutS(e.target.value)}
                placeholder="60"
              />
            </Field>
            <Field label={t("Max steps per case")}>
              <Input
                type="number"
                min={3}
                max={100}
                value={maxSteps}
                onChange={(e) => setMaxSteps(e.target.value)}
                placeholder="30"
              />
            </Field>
            <Field label={t("Parallel cases")}>
              <Input
                type="number"
                min={1}
                max={16}
                value={concurrency}
                onChange={(e) => setConcurrency(e.target.value)}
                placeholder="2"
              />
            </Field>
          </div>
          <Button onClick={saveRun} disabled={savingRun}>
            {savingRun ? t("Saving…") : t("Save changes")}
          </Button>
        </Card>

        {feishuEnabled && (
        <Card className="space-y-3 p-4">
          <div>
            <div className="text-sm font-medium text-ink-900">{t("Feishu bot")}</div>
            <div className="mt-0.5 text-xs text-ink-500">
              {t("Bind a Feishu group to this project: problems raised there attach here, and runs/results route to it. Or send \"@bot 绑定 <project>\" in the group.")}
            </div>
          </div>
          <Field label={t("Feishu group chat_id")}>
            <Input
              value={feishuChatId}
              onChange={(e) => setFeishuChatId(e.target.value)}
              placeholder="oc_xxxxxxxx"
            />
          </Field>
          <Field
            label={
              bitableBound
                ? t("Feishu Bitable link (bound — paste to change)")
                : t("Feishu Bitable link (feedback mirrors here)")
            }
          >
            <Input
              value={bitableUrl}
              onChange={(e) => setBitableUrl(e.target.value)}
              placeholder={bitableBound ? "已绑定 ✓" : "https://…feishu.cn/base/…?table=tbl…"}
            />
          </Field>
          <Button onClick={saveFeishu} disabled={savingFeishu}>
            {savingFeishu ? t("Saving…") : t("Save changes")}
          </Button>
        </Card>
        )}

        <Card className="space-y-3 p-4">
          <div>
            <div className="text-sm font-medium text-ink-900">{t("Environments")}</div>
            <div className="mt-0.5 text-xs text-ink-500">
              {t("Targets to run against (dev / test / prod), each with its own base URL and accounts.")}
            </div>
          </div>
          {envs.length > 0 ? (
            <div className="divide-y divide-[var(--line)] rounded-lg border border-[var(--line)]">
              {envs.map((e) =>
                editEnv?.id === e.id ? (
                  <div key={e.id} className="flex items-center gap-2 px-3 py-2">
                    <div className="w-32 shrink-0">
                      <Input
                        value={editEnv.name}
                        onChange={(ev) => setEditEnv({ ...editEnv, name: ev.target.value })}
                        className="h-8"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <Input
                        value={editEnv.base_url}
                        onChange={(ev) => setEditEnv({ ...editEnv, base_url: ev.target.value })}
                        placeholder="https://…"
                        className="h-8"
                      />
                    </div>
                    <Button size="sm" onClick={saveEnvEdit}>
                      {t("Save")}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setEditEnv(null)}>
                      {t("Cancel")}
                    </Button>
                  </div>
                ) : (
                  <div key={e.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                    <span className="font-medium text-ink-900">{e.name}</span>
                    {e.is_default && <Badge status="running">{t("default")}</Badge>}
                    <span className="truncate text-xs text-ink-500">{e.base_url ?? t("no base url")}</span>
                    <span className="shrink-0 text-xs text-ink-400">
                      {lang === "zh" ? `${envAccounts(e.id)} 个专属账号` : `${envAccounts(e.id)} dedicated`}
                    </span>
                    <span className="ml-auto flex gap-1">
                      {!e.is_default && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => api.updateEnvironment(e.id, { is_default: true }).then(loadEnvs)}
                        >
                          {t("Set default")}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setEditEnv({ id: e.id, name: e.name, base_url: e.base_url ?? "" })}
                      >
                        {t("Edit")}
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() =>
                          api.deleteEnvironment(e.id).then(loadEnvs).catch((err) => toast("error", String(err)))
                        }
                      >
                        {t("Delete")}
                      </Button>
                    </span>
                  </div>
                ),
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-[var(--line)] px-3 py-6 text-center text-xs text-ink-400">
              {lang === "zh"
                ? "暂无环境。此项为可选配置，未配置时用例默认使用项目基础 URL。"
                : "No environments yet. Optional — cases run against the project Base URL by default."}
            </div>
          )}
          <div className="flex items-end gap-2">
            <Field label={lang === "zh" ? "名称" : "Name"}>
              <Input value={newEnvName} onChange={(e) => setNewEnvName(e.target.value)} placeholder="test / prod" className="w-32" />
            </Field>
            <div className="flex-1">
              <Field label={t("Base URL")}>
                <Input value={newEnvUrl} onChange={(e) => setNewEnvUrl(e.target.value)} placeholder="https://your-app.example.com" />
              </Field>
            </div>
            <Button variant="outline" onClick={addEnv}>{t("Add environment")}</Button>
          </div>
        </Card>

        <Card className="space-y-3 p-4">
          <div>
            <div className="text-sm font-medium text-ink-900">{t("Roles")}</div>
            <div className="mt-0.5 text-xs text-ink-500">
              {t("Roles a case can run as. Bind each role to an account below; a case picks a role.")}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {roles.map((r) => {
              const n = roleAccounts(r);
              return (
                <span
                  key={r}
                  className={
                    "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium " +
                    (n === 0 ? "bg-[var(--bad-bg)] text-[var(--bad-fg)]" : "bg-brand-50 text-brand-700")
                  }
                  title={
                    n === 0
                      ? lang === "zh"
                        ? "该角色尚未绑定账号，使用该角色的用例将无法执行"
                        : "No account bound; cases using this role will fail"
                      : undefined
                  }
                >
                  {r}
                  <span className={n === 0 ? "opacity-90" : "text-brand-700/70"}>
                    {n === 0
                      ? lang === "zh"
                        ? "· 未绑定账号"
                        : "· no account"
                      : lang === "zh"
                        ? `· ${n} 个账号`
                        : `· ${n}`}
                  </span>
                  <button
                    onClick={() => saveRoles(roles.filter((x) => x !== r))}
                    className="opacity-60 hover:opacity-100"
                    aria-label={t("Remove")}
                  >
                    ×
                  </button>
                </span>
              );
            })}
            {roles.length === 0 && <span className="text-xs text-ink-400">{t("No roles yet.")}</span>}
          </div>
          <div className="flex gap-2">
            <Input
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addRole()}
              placeholder="requester / approver / admin"
              className="w-64"
            />
            <Button variant="outline" onClick={addRole}>{t("Add role")}</Button>
          </div>
        </Card>

        <CredentialsSection pid={pid} roles={roles} envs={envs} onChanged={loadCreds} />

        {gitlabEnabled && <GitLabSection pid={pid} />}
      </div>
    </div>
  );
}
