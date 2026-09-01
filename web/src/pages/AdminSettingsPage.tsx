import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type FeishuStatus } from "../lib/api";
import { Button, Card, Checkbox, Field, Input } from "../components/ui";
import { useToast } from "../components/toast";

export function AdminSettingsPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const [tokenSet, setTokenSet] = useState(false);
  const [token, setToken] = useState("");
  const [saving, setSaving] = useState(false);

  // Feishu
  const [fs, setFs] = useState<FeishuStatus | null>(null);
  const [appId, setAppId] = useState("");
  const [apiBase, setApiBase] = useState("https://open.feishu.cn");
  const [autoAnswer, setAutoAnswer] = useState(true);
  const [appSecret, setAppSecret] = useState("");
  const [verifToken, setVerifToken] = useState("");
  const [savingFs, setSavingFs] = useState(false);

  const webhookUrl = `${window.location.origin}/api/feishu/events`;

  const load = () =>
    api
      .getAdminSettings()
      .then((s) => {
        setTokenSet(s.gitlab_token_set);
        setFs(s.feishu);
        setAppId(s.feishu.app_id);
        setApiBase(s.feishu.api_base);
        setAutoAnswer(s.feishu.auto_answer_detected);
      })
      .catch(() => {});
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.setGitlabToken(token.trim());
      setTokenSet(r.gitlab_token_set);
      setToken("");
      toast("success", t("Saved"));
    } catch (e) {
      toast("error", String(e));
    } finally {
      setSaving(false);
    }
  };

  const saveFeishu = async () => {
    setSavingFs(true);
    try {
      const r = await api.setFeishuSettings({
        app_id: appId.trim(),
        api_base: apiBase.trim(),
        auto_answer_detected: autoAnswer,
        app_secret: appSecret.trim() || undefined,
        verification_token: verifToken.trim() || undefined,
      });
      setFs(r);
      setAppSecret("");
      setVerifToken("");
      toast("success", t("Saved"));
    } catch (e) {
      toast("error", String(e));
    } finally {
      setSavingFs(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">{t("System settings")}</h1>
        <p className="mt-1 text-sm text-ink-500">{t("Server-wide configuration (admin only).")}</p>
      </div>

      <Card className="max-w-2xl space-y-3 p-4">
        <div>
          <div className="text-sm font-medium text-ink-900">{t("Global GitLab token")}</div>
          <div className="text-xs text-ink-500">
            {t("An api-scope token used for GitLab sync across all projects. Projects then only pick a GitLab project.")}
          </div>
        </div>
        <Field label={tokenSet ? t("Access token (set — leave blank to keep)") : t("Access token (api scope)")}>
          <Input type="password" value={token} onChange={(e) => setToken(e.target.value)}
            placeholder={tokenSet ? "••••••••" : "glpat-…"} />
        </Field>
        <div className="flex items-center gap-3">
          <Button onClick={save} disabled={saving}>{saving ? t("Saving…") : t("Save")}</Button>
          <span className="text-xs text-ink-500">
            {tokenSet ? t("A global token is set.") : t("No global token set.")}
          </span>
          {tokenSet && (
            <button className="text-xs text-[var(--bad-fg)] hover:underline"
              onClick={() => api.setGitlabToken("").then(() => setTokenSet(false)).catch((e) => toast("error", String(e)))}>
              {t("Clear")}
            </button>
          )}
        </div>
        <p className="text-xs text-ink-500">{t("Stored encrypted; never returned. Enter it here — not in code.")}</p>
      </Card>

      <Card className="max-w-2xl space-y-3 p-4">
        <div>
          <div className="text-sm font-medium text-ink-900">{t("Feishu bot")}</div>
          <div className="text-xs text-ink-500">
            {t("Collect problems from a Feishu chat into Feedback / Issues. Configure the self-built app here.")}
          </div>
        </div>

        <div className="rounded-lg bg-[var(--panel2)] px-3 py-2 text-xs text-ink-700">
          <div>{t("Long-connection mode needs no callback URL — just the app credentials below.")}</div>
          <div className="mt-1 text-ink-500">
            {t("(Webhook mode only) Event subscription URL:")}{" "}
            <code className="break-all font-mono text-brand-700">{webhookUrl}</code>
          </div>
        </div>

        <Field label={t("App ID")}>
          <Input value={appId} onChange={(e) => setAppId(e.target.value)} placeholder="cli_xxx" />
        </Field>
        <Field label={fs?.app_secret_set ? t("App Secret (set — leave blank to keep)") : t("App Secret")}>
          <Input type="password" value={appSecret} onChange={(e) => setAppSecret(e.target.value)}
            placeholder={fs?.app_secret_set ? "••••••••" : ""} />
        </Field>
        <Field label={fs?.verification_token_set ? t("Verification Token (set — leave blank to keep)") : t("Verification Token")}>
          <Input type="password" value={verifToken} onChange={(e) => setVerifToken(e.target.value)}
            placeholder={fs?.verification_token_set ? "••••••••" : ""} />
        </Field>
        <Field label={t("API base")}>
          <Input value={apiBase} onChange={(e) => setApiBase(e.target.value)}
            placeholder="https://open.feishu.cn" />
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink-700">
          <Checkbox checked={autoAnswer} onChange={(e) => setAutoAnswer(e.target.checked)} />
          {t("Auto-answer context-detected questions (not just @-mentions)")}
        </label>

        <div className="flex items-center gap-3">
          <Button onClick={saveFeishu} disabled={savingFs}>{savingFs ? t("Saving…") : t("Save")}</Button>
          <span className="text-xs text-ink-500">
            {fs?.app_secret_set ? t("Bot credentials are set.") : t("Bot not configured yet.")}
          </span>
        </div>
        <p className="text-xs text-ink-500">
          {t("Secrets stored encrypted; never returned. Leave the Encrypt Key blank in the Feishu console.")}
        </p>
      </Card>
    </div>
  );
}
