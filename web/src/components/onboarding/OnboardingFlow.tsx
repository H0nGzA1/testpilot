import { PlayCircle, Rocket } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { Button, Card } from "../ui";
import { useToast } from "../toast";
import {
  AccountStep,
  CaptureGate,
  CaseStep,
  ProjectStep,
  Spinner,
  StepRail,
  useProjectSetup,
} from "./setupSteps";

/** The guided first-run flow: a full-screen welcome, then four steps ending in a real
 *  run and a real report.
 *
 *  This exists because the first version of onboarding was assembled from five pieces
 *  that each triggered on their own condition (zero projects / a click / an empty
 *  overview / a project's first case / a project's first run). Every piece was correct
 *  on its own and the whole was invisible: nothing greeted you on sign-in, and at no
 *  point could you see how far along you were. So the same four things are now one
 *  visible spine with a step count.
 *
 *  The per-project SetupChecklist stays — it's what catches someone who skips this. */
export function OnboardingFlow({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const nav = useNavigate();
  const s = useProjectSetup();

  // 0 = welcome screen, 1..4 = the steps
  const [step, setStep] = useState(0);
  const [running, setRunning] = useState(false);

  const labels = [t("Create project"), t("Add account"), t("Write a case"), t("Run it")];

  const next = () => setStep((n) => n + 1);

  const submitProject = async () => (await s.createProject()) && next();
  const submitCase = async () => (await s.createStarterCase()) && next();

  /** Step 4 — the payoff. Kicks off a real run and hands over to the live report, which
   *  already streams results and coaches on what to do with them. */
  const startRun = async () => {
    if (!s.project) return;
    setRunning(true);
    try {
      const run = await api.createRun(s.project.id, { name: t("First run") });
      onClose();
      nav(`/projects/${s.project.id}/runs/${run.id}`);
    } catch (e) {
      toast("error", String(e));
      setRunning(false);
    }
  };

  const finishWithoutRunning = () => {
    onClose();
    if (s.project) nav(`/projects/${s.project.id}/cases`);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-[var(--surface)]">
      <div className="mx-auto flex min-h-full w-full max-w-2xl flex-col justify-center px-6 py-10">
        {step === 0 ? (
          <div className="text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-brand-600 text-[var(--on-brand)]">
              <Rocket className="h-6 w-6" />
            </div>
            <h1 className="mt-5 text-2xl font-semibold text-ink-900">{t("Welcome to TestPilot")}</h1>
            <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-ink-500">
              {t("You write test cases as plain-language tasks. An agent carries each one out in a real browser, records a video, and a judge decides pass or fail.")}
            </p>

            <div className="mx-auto mt-7 grid max-w-md gap-2 text-left">
              {labels.map((l, i) => (
                <div
                  key={l}
                  className="flex items-center gap-3 rounded-lg border border-[var(--line)] bg-[var(--panel)] px-3 py-2.5"
                >
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-50 text-[11px] font-medium text-brand-700">
                    {i + 1}
                  </span>
                  <span className="text-sm text-ink-700">{l}</span>
                </div>
              ))}
            </div>

            <Button className="mt-7" onClick={() => setStep(1)}>
              {t("Start — 4 steps, about 10 minutes")}
            </Button>
            <div>
              <button
                onClick={onClose}
                className="mt-3 text-xs text-ink-500 underline-offset-2 hover:text-ink-900 hover:underline"
              >
                {t("Skip — I'll look around myself")}
              </button>
            </div>
          </div>
        ) : (
          <Card className="p-6">
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <h2 className="text-lg font-semibold text-ink-900">{labels[step - 1]}</h2>
              <span className="shrink-0 text-xs tabular-nums text-ink-500">
                {t("Step {{n}} of {{total}}", { n: step, total: labels.length })}
              </span>
            </div>
            <div className="mb-5 mt-3">
              <StepRail labels={labels} current={step} captured={s.captured} compact />
            </div>

            <div className="space-y-4">
              {step === 1 && (
                <>
                  <p className="text-xs leading-relaxed text-ink-500">
                    {t("A project holds the cases for one system under test.")}
                  </p>
                  <ProjectStep s={s} onSubmit={submitProject} />
                  <Foot>
                    <Button variant="ghost" onClick={onClose}>
                      {t("Skip setup")}
                    </Button>
                    <Button onClick={submitProject} disabled={s.busy}>
                      {s.busy && <Spinner />}
                      {t("Next")}
                    </Button>
                  </Foot>
                </>
              )}

              {step === 2 && (
                <>
                  <AccountStep s={s} />
                  <Foot>
                    <Button variant="outline" onClick={next}>
                      {s.captured ? t("Next") : t("Skip — the site needs no login")}
                    </Button>
                    <Button
                      onClick={() => s.setCapturing(true)}
                      disabled={!s.username.trim() || !s.password}
                    >
                      {t("Log in & capture session")}
                    </Button>
                  </Foot>
                </>
              )}

              {step === 3 && (
                <>
                  <CaseStep s={s} onImported={next} />
                  <Foot>
                    <Button variant="outline" onClick={() => setStep(2)}>
                      {t("Back")}
                    </Button>
                    <Button onClick={submitCase} disabled={s.busy}>
                      {s.busy && <Spinner />}
                      {t("Next")}
                    </Button>
                  </Foot>
                </>
              )}

              {step === 4 && (
                <>
                  <p className="text-sm leading-relaxed text-ink-700">
                    {t("That's the setup. Running it launches a real Chrome, drives it through your case and records video — the first result takes roughly 30–90 seconds, and you'll watch it stream in.")}
                  </p>
                  {!s.captured && (
                    <p className="rounded-lg bg-[var(--warn-bg)] px-3 py-2 text-xs text-[var(--warn-fg)]">
                      {t("You skipped the account step, so anything behind a login will fail. That's fine for a first look — add an account in Settings when you need it.")}
                    </p>
                  )}
                  <Foot>
                    <Button variant="ghost" onClick={finishWithoutRunning}>
                      {t("Finish without running")}
                    </Button>
                    <Button onClick={startRun} disabled={running}>
                      {running ? <Spinner /> : <PlayCircle className="h-4 w-4" />}
                      {t("Run it now")}
                    </Button>
                  </Foot>
                </>
              )}
            </div>
          </Card>
        )}
      </div>

      <CaptureGate s={s} onDismiss={() => s.captured && next()} />
    </div>
  );
}

function Foot({ children }: { children: React.ReactNode }) {
  return <div className="flex justify-end gap-2 pt-2">{children}</div>;
}
