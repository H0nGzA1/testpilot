import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import { Button } from "./ui";

/** Progress modal for the server-side "log in & capture session" flow. The capture is
 *  a single request with no streaming, so this shows an indeterminate spinner + an
 *  elapsed timer + staged hints, then a clear success / failure result (option A). */
export function CaptureProgressModal({
  pid,
  username,
  password,
  label,
  onClose,
  onDone,
}: {
  pid: number;
  username: string;
  password: string;
  label: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<"running" | "success" | "error">("running");
  const [err, setErr] = useState("");
  const [elapsed, setElapsed] = useState(0);

  // elapsed timer
  useEffect(() => {
    if (status !== "running") return;
    const iv = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(iv);
  }, [status]);

  const run = () => {
    setErr("");
    setElapsed(0);
    setStatus("running");
    api
      .captureCredential(pid, { label: label || undefined, username, password })
      .then(() => {
        setStatus("success");
        onDone();
      })
      .catch((e) => {
        setErr(String(e));
        setStatus("error");
      });
  };

  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const running = status === "running";
  const stage =
    elapsed < 4
      ? t("Starting the browser…")
      : elapsed < 12
        ? t("Opening the target site and signing in…")
        : t("Reading the captcha and capturing the session…");
  const mmss = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6"
      onClick={() => !running && onClose()}
    >
      <div
        className="w-full max-w-sm overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-3.5">
          <span className="text-sm font-medium text-ink-900">{t("Log in & capture session")}</span>
          {!running && (
            <button onClick={onClose} className="text-ink-500 hover:text-ink-900">
              ✕
            </button>
          )}
        </div>
        <div className="flex flex-col items-center px-6 py-7 text-center">
          {running && (
            <>
              <div className="h-11 w-11 animate-spin rounded-full border-[3px] border-[var(--panel2)] border-t-brand-600" />
              <div className="mt-4 text-sm font-medium text-ink-900">{stage}</div>
              <div className="mt-1 text-xs tabular-nums text-ink-500">{t("Elapsed {{t}}", { t: mmss })}</div>
              <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-[var(--panel2)]">
                <div className="tp-indeterminate h-full w-2/5 rounded-full bg-brand-600" />
              </div>
              <div className="mt-3.5 text-xs leading-relaxed text-ink-500">
                {t("The server is signing in and capturing the session — first run takes ~30-60s. Please keep this window open.")}
              </div>
            </>
          )}
          {status === "success" && (
            <>
              <div className="grid h-11 w-11 place-items-center rounded-full bg-[var(--ok-bg)] text-xl text-[var(--ok-fg)]">✓</div>
              <div className="mt-3.5 text-[15px] font-semibold text-ink-900">{t("Session captured")}</div>
              <div className="mt-1.5 text-[13px] leading-relaxed text-ink-500">
                {t("The credential is saved and set active. You can run test cases now.")}
              </div>
              <Button className="mt-5" onClick={onClose}>
                {t("Done")}
              </Button>
            </>
          )}
          {status === "error" && (
            <>
              <div className="grid h-11 w-11 place-items-center rounded-full bg-[var(--bad-bg)] text-xl text-[var(--bad-fg)]">✕</div>
              <div className="mt-3.5 text-[15px] font-semibold text-ink-900">{t("Sign-in failed")}</div>
              <div className="mt-1.5 max-h-28 overflow-auto text-[13px] leading-relaxed text-ink-500">
                {err || t("Could not complete sign-in on the target site. Check the account/password and retry.")}
              </div>
              <div className="mt-5 flex gap-2">
                <Button variant="outline" onClick={onClose}>
                  {t("Close")}
                </Button>
                <Button onClick={run}>{t("Retry")}</Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
