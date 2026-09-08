import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import { Button, Card, Field, Input } from "./ui";
import { Modal } from "./Modal";
import { useToast } from "./toast";

/** Self-serve password change from the account menu — needs the current password. */
export function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (close: () => void, e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await api.changePassword({ old_password: oldPw, new_password: newPw });
      toast("success", t("Password changed."));
      close();
    } catch {
      setErr(t("Current password is incorrect."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose} className="max-w-sm">
      {(close) => (
        <Card className="p-5">
          <div className="text-base font-semibold text-ink-900">{t("Change password")}</div>
          <form onSubmit={(e) => submit(close, e)} className="mt-3 space-y-3">
            <Field label={t("Current password")}>
              <Input type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} autoFocus />
            </Field>
            <Field label={t("New password (min 6 chars)")}>
              <Input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
            </Field>
            <Field label={t("Confirm new password")}>
              <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </Field>
            {confirm && confirm !== newPw && (
              <div className="text-xs text-[var(--bad-fg)]">{t("The two passwords don't match.")}</div>
            )}
            {err && (
              <div className="rounded-lg bg-[var(--bad-bg)] px-3 py-2 text-sm text-[var(--bad-fg)]">{err}</div>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="ghost" onClick={close}>
                {t("Cancel")}
              </Button>
              <Button type="submit" disabled={busy || !oldPw || newPw.length < 6 || confirm !== newPw}>
                {busy ? t("Saving…") : t("Save")}
              </Button>
            </div>
          </form>
        </Card>
      )}
    </Modal>
  );
}
