import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, relTime, type Credential, type Environment } from "../lib/api";
import { Badge, Button, Card, Field, Input, Select, Textarea } from "./ui";
import { CaptureProgressModal } from "./CaptureProgressModal";
import { useToast } from "./toast";

export function CredentialsSection({
  pid,
  roles: propRoles,
  envs = [],
  onChanged,
}: {
  pid: number;
  roles?: string[];
  envs?: Environment[];
  onChanged?: () => void;
}) {
  const toast = useToast();
  const { t } = useTranslation();
  const [creds, setCreds] = useState<Credential[]>([]);
  const [fetchedRoles, setFetchedRoles] = useState<string[]>([]);
  const roles = propRoles ?? fetchedRoles;
  const [type, setType] = useState<"storage_state" | "password">("password");
  const [role, setRole] = useState("");
  const [envId, setEnvId] = useState("");
  const envName = (id: number | null) => envs.find((e) => e.id === id)?.name;
  const [label, setLabel] = useState("");
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [capture, setCapture] = useState<{ username: string; password: string; label: string; role: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () =>
    api
      .listCredentials(pid)
      .then((c) => {
        setCreds(c);
        onChanged?.();
      })
      .catch((e) => toast("error", String(e)));
  useEffect(() => {
    load();
    if (!propRoles) api.getRoles(pid).then((r) => setFetchedRoles(r.roles)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  const reset = () => {
    setLabel("");
    setUsername("");
    setSecret("");
    setRole("");
    setEnvId("");
  };

  const add = async () => {
    if (type === "password") {
      if (!username.trim() || !secret.trim()) {
        toast("error", t("Enter the test account username and password"));
        return;
      }
      // role accounts are stored directly (the agent prompt-logs in per case); the
      // default account (no role) goes through capture to validate + snapshot the session.
      if (role) {
        setSaving(true);
        try {
          await api.createCredential(pid, {
            type: "password",
            role,
            environment_id: envId ? Number(envId) : undefined,
            label: label || undefined,
            username,
            secret,
          });
          toast("success", t("Account saved"));
          reset();
          load();
        } catch (e) {
          toast("error", String(e));
        } finally {
          setSaving(false);
        }
        return;
      }
      setCapture({ username, password: secret, label, role });
      return;
    }
    if (!secret.trim()) {
      toast("error", "Paste or upload the login state");
      return;
    }
    setSaving(true);
    try {
      await api.createCredential(pid, {
        type,
        role: role || undefined,
        environment_id: envId ? Number(envId) : undefined,
        label: label || undefined,
        secret,
      });
      toast("success", t("Credential saved & activated"));
      reset();
      load();
    } catch (e) {
      toast("error", String(e));
    } finally {
      setSaving(false);
    }
  };

  const onFile = async (f: File) => {
    setSecret(await f.text());
    if (!label) setLabel(f.name.replace(/\.json$/i, ""));
  };

  const [rechecking, setRechecking] = useState<number | null>(null);
  const recheck = async (cid: number) => {
    setRechecking(cid);
    try {
      await api.recheckCredential(cid);
      toast("success", t("Account re-checked"));
      load();
    } catch (e) {
      toast("error", String(e));
      load();
    } finally {
      setRechecking(null);
    }
  };

  return (
    <Card className="space-y-4 p-4">
      <div>
        <div className="text-sm font-medium text-ink-900">{t("Credentials")}</div>
        <div className="text-xs text-ink-500">
          {t("Logins used to reach the app under test. Stored encrypted; the active one is injected at run time.")}
        </div>
      </div>

      {creds.length > 0 && (
        <div className="divide-y divide-[var(--line)] rounded-lg border border-[var(--line)]">
          {creds.map((c) => (
            <div key={c.id} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${c.healthy ? "bg-[var(--ok-fg)]" : "bg-[var(--bad-fg)]"}`}
                title={c.healthy ? t("healthy") : c.last_error ?? t("unhealthy")}
              />
              <span className="font-medium text-ink-900">{c.label || c.type}</span>
              {c.role && (
                <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700">
                  {c.role}
                </span>
              )}
              {c.environment_id != null && envName(c.environment_id) && (
                <span className="rounded-full bg-[var(--panel2)] px-2 py-0.5 text-[11px] text-ink-600">
                  {envName(c.environment_id)}
                </span>
              )}
              <span className="rounded-full bg-[var(--panel2)] px-2 py-0.5 text-[11px] text-ink-500">
                {c.type === "password" ? `${t("session")}: ${c.username}` : t("session")}
              </span>
              {c.is_active && <Badge status="passed">{t("active")}</Badge>}
              <span className="ml-auto text-xs text-ink-500">{relTime(c.created_at)}</span>
              {c.type === "password" && (
                <Button size="sm" variant="outline" disabled={rechecking === c.id} onClick={() => recheck(c.id)}>
                  {rechecking === c.id ? t("Checking…") : t("Re-check")}
                </Button>
              )}
              {!c.is_active && (
                <Button size="sm" variant="outline" onClick={() => api.activateCredential(c.id).then(load)}>
                  {t("Activate")}
                </Button>
              )}
              <Button
                size="sm"
                variant="danger"
                onClick={() => api.deleteCredential(c.id).then(load).catch((e) => toast("error", String(e)))}
              >
                {t("Delete")}
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-3 rounded-lg border border-dashed border-[var(--line)] p-3">
        <div className="flex items-center gap-3">
          <Field label={t("Type")}>
            <Select
              value={type}
              onChange={(e) => setType(e.target.value as "storage_state" | "password")}
            >
              <option value="password">{t("Test account — auto login (recommended)")}</option>
              <option value="storage_state">{t("Session snapshot (advanced)")}</option>
            </Select>
          </Field>
          <Field label={t("Role (optional)")}>
            <Select value={role} onValueChange={setRole}>
              <option value="">{t("— default account —")}</option>
              {roles.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </Select>
          </Field>
          {envs.length > 0 && (
            <Field label={t("Environment")}>
              <Select value={envId} onValueChange={setEnvId}>
                <option value="">{t("— any environment —")}</option>
                {envs.map((e) => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </Select>
            </Field>
          )}
          <div className="flex-1">
            <Field label={t("Label (optional)")}>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. staging session" />
            </Field>
          </div>
        </div>

        {type === "password" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("Username")}>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="robot test account" />
            </Field>
            <Field label={t("Password")}>
              <Input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="••••••••" />
            </Field>
          </div>
        ) : (
          <Field label={t("storage_state JSON (upload auth.json or paste)")}>
            <div className="space-y-2">
              <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
                {t("Upload auth.json")}
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept="application/json,.json"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
              />
              <Textarea
                rows={3}
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder='{"cookies":[…],"origins":[…]}'
              />
            </div>
          </Field>
        )}

        <Button onClick={add} disabled={saving}>
          {saving
            ? type === "password"
              ? t("Logging in…")
              : t("Saving…")
            : type === "password"
              ? t("Log in & capture session")
              : t("Save credential")}
        </Button>
        <p className="text-xs text-ink-500">
          {type === "password"
            ? t("The server logs into the project's Base URL with this account and captures the session (simple captchas are read automatically). No local setup needed.")
            : "Advanced: paste/upload a storage_state you captured elsewhere. Requires TESTPILOT_SECRET_KEY on the server."}
        </p>
      </div>

      {capture && (
        <CaptureProgressModal
          pid={pid}
          username={capture.username}
          password={capture.password}
          label={capture.label}
          onClose={() => setCapture(null)}
          onDone={() => {
            reset();
            load();
          }}
        />
      )}
    </Card>
  );
}
