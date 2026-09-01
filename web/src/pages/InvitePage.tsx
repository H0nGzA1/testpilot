import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Card, Field, Input } from "../components/ui";

export function InvitePage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [email, setEmail] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getInvite(token)
      .then((i) => setEmail(i.email))
      .catch(() => setError(t("This invite is invalid, used, or expired.")));
  }, [token, t]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.acceptInvite(token, { name: name.trim(), password });
      await refresh();
      navigate("/");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--surface)] p-6">
      <Card className="w-full max-w-sm p-6">
        <div className="mb-1 text-lg font-semibold text-ink-900">{t("Activate your account")}</div>
        {error ? (
          <div className="mt-3 rounded-lg bg-[var(--bad-bg)] px-3 py-2 text-sm text-[var(--bad-fg)]">{error}</div>
        ) : email === null ? (
          <div className="mt-3 text-sm text-ink-500">{t("Loading…")}</div>
        ) : (
          <form onSubmit={submit} className="mt-3 space-y-3">
            <div className="text-sm text-ink-500">{email}</div>
            <Field label={t("Your name")}>
              <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
            </Field>
            <Field label={t("Set a password (min 6 chars)")}>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Button type="submit" disabled={busy || password.length < 6} className="w-full">
              {busy ? t("Activating…") : t("Activate & sign in")}
            </Button>
          </form>
        )}
      </Card>
    </div>
  );
}
