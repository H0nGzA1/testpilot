import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Card, Field, Input } from "../components/ui";

/** Landing page for a reset link (emailed by /auth/forgot or by an admin). The token is
 *  only checked on submit — the server never confirms an account exists before then. */
export function ResetPasswordPage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.resetPassword(token, password);
      await refresh();
      navigate("/");
    } catch {
      setError(t("This reset link is invalid, used, or expired. Request a new one."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--surface)] p-6">
      <Card className="w-full max-w-sm p-6">
        <div className="mb-1 text-lg font-semibold text-ink-900">{t("Set a new password")}</div>
        <form onSubmit={submit} className="mt-3 space-y-3">
          <Field label={t("New password (min 6 chars)")}>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
          </Field>
          <Field label={t("Confirm new password")}>
            <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          {confirm && confirm !== password && (
            <div className="text-xs text-[var(--bad-fg)]">{t("The two passwords don't match.")}</div>
          )}
          {error && (
            <div className="rounded-lg bg-[var(--bad-bg)] px-3 py-2 text-sm text-[var(--bad-fg)]">{error}</div>
          )}
          <Button type="submit" disabled={busy || password.length < 6 || confirm !== password} className="w-full">
            {busy ? t("Saving…") : t("Set password & sign in")}
          </Button>
        </form>
        <Link to="/login" className="mt-3 block text-center text-xs text-ink-500 hover:text-ink-900">
          {t("Back to sign in")}
        </Link>
      </Card>
    </div>
  );
}
