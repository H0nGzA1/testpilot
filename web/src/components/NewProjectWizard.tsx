import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button, Card } from "./ui";
import { Modal } from "./Modal";
import {
  AccountStep,
  CaptureGate,
  CaseStep,
  Foot,
  ProjectStep,
  Spinner,
  StepRail,
  useProjectSetup,
} from "./onboarding/setupSteps";

/** "New project" for someone who already knows what TestPilot is — the same three
 *  setup steps as the guided first-run flow (shared via useProjectSetup), minus the
 *  welcome screen and the run, in a modal instead of full screen. */
export function NewProjectWizard({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const s = useProjectSetup();
  const [step, setStep] = useState(1);

  const labels = [t("Project"), t("Account"), t("First case")];

  const submitProject = async () => (await s.createProject()) && setStep(2);

  const finish = async () => {
    if (!(await s.createStarterCase())) return;
    onDone();
    if (s.project) nav(`/projects/${s.project.id}/cases`);
  };

  return (
    <>
      <Modal onClose={onClose} className="max-w-lg">
        <Card className="p-5">
          <h2 className="text-lg font-semibold text-ink-900">{t("New project")}</h2>

          <div className="mt-4">
            <StepRail labels={labels} current={step} captured={s.captured} />
          </div>

          <div className="mt-5 space-y-4">
            {step === 1 && (
              <>
                <ProjectStep s={s} onSubmit={submitProject} />
                <Foot>
                  <Button variant="outline" onClick={onClose}>
                    {t("Cancel")}
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
                  <Button variant="outline" onClick={() => setStep(3)}>
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
                <CaseStep s={s} onImported={finish} />
                <Foot>
                  <Button variant="outline" onClick={() => setStep(2)}>
                    {t("Back")}
                  </Button>
                  <Button onClick={finish} disabled={s.busy}>
                    {s.busy && <Spinner />}
                    {s.seedCase ? t("Create case & finish") : t("Finish")}
                  </Button>
                </Foot>
              </>
            )}
          </div>
        </Card>
      </Modal>

      <CaptureGate s={s} onDismiss={() => s.captured && setStep(3)} />
    </>
  );
}
