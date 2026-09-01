import { Check, Loader2 } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { api, type Project } from "../../lib/api";
import { Button, Checkbox, Field, Input } from "../ui";
import { CaptureProgressModal } from "../CaptureProgressModal";
import { useToast } from "../toast";

/** The three things a project needs before anything can run — project, account, first
 *  case — as one piece of state plus three form bodies.
 *
 *  Two shells consume this: the modal `NewProjectWizard` (an existing user adding
 *  another project) and the full-screen `OnboardingFlow` (a user's first sign-in, which
 *  wraps these in a welcome screen and a fourth "run it" step). Keeping the forms here
 *  means the two can't drift apart. */

export type Setup = ReturnType<typeof useProjectSetup>;

export function useProjectSetup() {
  const { t } = useTranslation();
  const toast = useToast();

  const [project, setProject] = useState<Project | null>(null);
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [capturing, setCapturing] = useState(false);
  const [captured, setCaptured] = useState(false);
  const [seedCase, setSeedCase] = useState(true);
  const [caseCount, setCaseCount] = useState(0);

  // The starter case: a smoke check against the base URL. Deliberately trivial — its
  // job is to give the user something runnable in one click so they see what a report
  // actually looks like.
  const smokePrompt = t("Open {{url}} and wait for the home page to finish loading.", {
    url: baseUrl.trim() || t("the base URL"),
  });
  const smokeExpected = t("The main content is rendered — no error page, no blank screen.");

  /** Creates the project. Steps 2 and 3 are project-scoped (capture + case creation
   *  need a real id), so this has to happen before them; bailing out later leaves a
   *  valid, if bare, project that the Overview checklist picks up. */
  const createProject = async (): Promise<boolean> => {
    if (project) return true; // already created — re-entering step 1 shouldn't duplicate
    if (!name.trim()) {
      toast("error", t("Name is required"));
      return false;
    }
    setBusy(true);
    try {
      setProject(
        await api.createProject({ name: name.trim(), base_url: baseUrl.trim() || undefined }),
      );
      return true;
    } catch (e) {
      toast("error", String(e));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const createStarterCase = async (): Promise<boolean> => {
    if (!project || !seedCase) return true;
    setBusy(true);
    try {
      await api.createCase(project.id, {
        name: t("Smoke — home page loads"),
        prompt: smokePrompt,
        expected: smokeExpected,
        type: "smoke",
        tags: ["smoke"],
      });
      setCaseCount((n) => n + 1);
      setSeedCase(false); // idempotent: stepping back and forward won't make a second one
      return true;
    } catch (e) {
      toast("error", String(e));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const importXlsx = async (f: File): Promise<boolean> => {
    if (!project) return false;
    setBusy(true);
    try {
      const { imported } = await api.importCasesXlsx(project.id, f);
      toast("success", t("Imported {{n}} cases", { n: imported }));
      setCaseCount((n) => n + imported);
      setSeedCase(false);
      return true;
    } catch (e) {
      toast("error", String(e));
      return false;
    } finally {
      setBusy(false);
    }
  };

  return {
    t,
    project,
    busy,
    name,
    setName,
    baseUrl,
    setBaseUrl,
    username,
    setUsername,
    password,
    setPassword,
    capturing,
    setCapturing,
    captured,
    setCaptured,
    seedCase,
    setSeedCase,
    caseCount,
    smokePrompt,
    smokeExpected,
    createProject,
    createStarterCase,
    importXlsx,
  };
}

export function ProjectStep({ s, onSubmit }: { s: Setup; onSubmit: () => void }) {
  const { t } = s;
  return (
    <>
      <Field label={t("Name")}>
        <Input
          value={s.name}
          onChange={(e) => s.setName(e.target.value)}
          placeholder="e.g. Web regression"
          autoFocus
          disabled={!!s.project}
          onKeyDown={(e) => e.key === "Enter" && onSubmit()}
        />
      </Field>
      <Field label={t("Base URL")}>
        <Input
          value={s.baseUrl}
          onChange={(e) => s.setBaseUrl(e.target.value)}
          placeholder="https://your-app.example.com"
          disabled={!!s.project}
          onKeyDown={(e) => e.key === "Enter" && onSubmit()}
        />
      </Field>
      <p className="text-xs text-ink-500">
        {t("Where every case starts unless it overrides it. You can change this later in Settings.")}
      </p>
    </>
  );
}

export function AccountStep({ s }: { s: Setup }) {
  const { t } = s;
  return (
    <>
      <p className="text-xs leading-relaxed text-ink-500">
        {t("The agent signs in once and reuses the session. Without an account it can only reach pages that need no login.")}
      </p>
      <Field label={t("Username")}>
        <Input value={s.username} onChange={(e) => s.setUsername(e.target.value)} autoFocus />
      </Field>
      <Field label={t("Password")}>
        <Input
          type="password"
          value={s.password}
          onChange={(e) => s.setPassword(e.target.value)}
        />
      </Field>
      {s.captured && (
        <div className="flex items-center gap-1.5 text-xs text-brand-700">
          <Check className="h-3.5 w-3.5" />
          {t("Session captured.")}
        </div>
      )}
    </>
  );
}

export function CaseStep({ s, onImported }: { s: Setup; onImported?: () => void }) {
  const { t } = s;
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <p className="text-xs leading-relaxed text-ink-500">
        {t("A case is a task in plain language plus one line saying what counts as a pass. Start with the smoke case below — you can run it right away and see what a report looks like.")}
      </p>
      {s.caseCount > 0 ? (
        <div className="flex items-center gap-1.5 rounded-lg border border-brand-100 bg-brand-50 px-3 py-2.5 text-sm text-ink-700">
          <Check className="h-4 w-4 shrink-0 text-brand-600" />
          {t("{{n}} case(s) ready.", { n: s.caseCount })}
        </div>
      ) : (
        <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-[var(--line)] p-3 hover:bg-brand-50">
          <Checkbox
            className="mt-0.5"
            checked={s.seedCase}
            onChange={(e) => s.setSeedCase(e.target.checked)}
          />
          <span className="min-w-0 text-sm">
            <span className="font-medium text-ink-900">{t("Create a starter smoke case")}</span>
            <span className="mt-1 block text-xs text-ink-500">{s.smokePrompt}</span>
            <span className="mt-0.5 block text-xs text-ink-500">
              {t("Pass when:")} {s.smokeExpected}
            </span>
          </span>
        </label>
      )}
      <div className="flex items-center gap-3 text-xs text-ink-500">
        <span>{t("Already have cases in a spreadsheet?")}</span>
        <button
          className="font-medium text-brand-700 hover:underline"
          onClick={() => fileRef.current?.click()}
        >
          {t("Import Excel")}
        </button>
        {s.project && (
          <a href={api.templateUrl(s.project.id)} className="text-brand-700 hover:underline">
            {t("Download template")}
          </a>
        )}
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={(e) =>
            e.target.files?.[0] && s.importXlsx(e.target.files[0]).then((ok) => ok && onImported?.())
          }
        />
      </div>
    </>
  );
}

/** Renders the capture modal when the account step asks for it. The modal shows its own
 *  success screen; its Done/✕ is what advances the caller (via onDismiss). */
export function CaptureGate({ s, onDismiss }: { s: Setup; onDismiss: () => void }) {
  if (!s.capturing || !s.project) return null;
  return (
    <CaptureProgressModal
      pid={s.project.id}
      username={s.username}
      password={s.password}
      label={s.username}
      onDone={() => s.setCaptured(true)}
      onClose={() => {
        s.setCapturing(false);
        onDismiss();
      }}
    />
  );
}

/** Numbered progress rail. `state` per step: done / skipped / current / todo. */
export function StepRail({
  labels,
  current,
  captured,
  compact,
}: {
  labels: string[];
  current: number;
  /** step 2 is skippable — "past it" is not the same as "done" */
  captured: boolean;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <ol className="flex items-center gap-2">
      {labels.map((label, i) => {
        const n = i + 1;
        const past = current > n;
        const done = past && (n !== 2 || captured);
        const skipped = past && !done;
        return (
          <li key={label} className="flex flex-1 items-center gap-2">
            <span
              className={
                "grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-medium " +
                (done
                  ? "bg-brand-600 text-[var(--on-brand)]"
                  : skipped
                    ? "bg-[var(--panel2)] text-ink-400"
                    : current === n
                      ? "bg-brand-50 text-brand-700 ring-1 ring-brand-500"
                      : "bg-[var(--panel2)] text-ink-400")
              }
            >
              {done ? <Check className="h-3.5 w-3.5" /> : skipped ? "–" : n}
            </span>
            {!compact && (
              <span
                className={
                  "truncate text-xs " +
                  (current === n ? "font-medium text-ink-900" : skipped ? "text-ink-400" : "text-ink-500")
                }
              >
                {label}
                {skipped && ` (${t("skipped")})`}
              </span>
            )}
            {n < labels.length && <span className="h-px flex-1 bg-[var(--line)]" />}
          </li>
        );
      })}
    </ol>
  );
}

export function Spinner() {
  return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
}

export function Foot({ children }: { children: ReactNode }) {
  return <div className="flex justify-end gap-2 pt-1">{children}</div>;
}

export { Button };
