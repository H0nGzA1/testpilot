import { PanelLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, type Project } from "../lib/api";
import { useOnboarding } from "../lib/useOnboarding";
import { OnboardingFlow } from "./onboarding/OnboardingFlow";
import { CommandPalette } from "./CommandPalette";
import { NotificationBell } from "./NotificationBell";
import { Sidebar } from "./Sidebar";
import { Select } from "./ui";

const SECTION_LABEL: Record<string, string> = {
  overview: "Overview",
  cases: "Test Cases",
  suites: "Suites",
  runs: "Runs",
  compare: "Compare",
  issues: "Issues",
  settings: "Settings",
};

export function Layout() {
  const { pid: pidParam } = useParams();
  const loc = useLocation();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [palette, setPalette] = useState(false);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("tp.sidebar") === "collapsed");
  const guide = useOnboarding();

  useEffect(() => {
    api.listProjects().then(setProjects).catch(() => {});
  }, [loc.pathname]);

  const toggleSidebar = () =>
    setCollapsed((v) => {
      localStorage.setItem("tp.sidebar", v ? "expanded" : "collapsed");
      return !v;
    });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      }
      // ⌘/Ctrl+B — the near-universal "toggle sidebar" shortcut
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const { t } = useTranslation();
  const pid = pidParam ? Number(pidParam) : null;
  const parts = loc.pathname.split("/");
  const section = parts[1] === "projects" ? (parts[3] ?? "overview") : null;
  const current = projects.find((p) => p.id === pid);

  return (
    <div className="flex min-h-screen">
      <Sidebar
        projects={projects}
        pid={pid}
        section={section}
        onSearch={() => setPalette(true)}
        collapsed={collapsed}
        onOpenGuide={guide.start}
      />
      <CommandPalette open={palette} onClose={() => setPalette(false)} projects={projects} pid={pid} />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-11 items-center gap-2 border-b border-[var(--line)] px-4 text-sm text-ink-500">
          <button
            onClick={toggleSidebar}
            title={`${t(collapsed ? "Expand sidebar" : "Collapse sidebar")} ⌘B`}
            aria-label={t(collapsed ? "Expand sidebar" : "Collapse sidebar")}
            className="-ml-1 rounded p-1 text-ink-500 hover:bg-[var(--panel2)] hover:text-ink-900"
          >
            <PanelLeft className="h-4 w-4" />
          </button>
          <span className="text-ink-700">TestPilot</span>
          {pid == null ? (
            <>
              <span>/</span>
              <span className="text-ink-900">{t("Projects")}</span>
            </>
          ) : (
            <>
              <span>/</span>
              <Select
                variant="bare"
                value={String(pid)}
                onChange={(e) => navigate(`/projects/${e.target.value}/${section ?? "overview"}`)}
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
              <span>/</span>
              <span className="text-ink-900">{t(SECTION_LABEL[section ?? "overview"] ?? section ?? "")}</span>
            </>
          )}
          <span className="ml-2 truncate text-ink-500">{current?.base_url ?? ""}</span>
          <div className="ml-auto">
            <NotificationBell />
          </div>
        </div>
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-6xl px-8 py-8">
            <Outlet />
          </div>
        </main>
      </div>
      {guide.open && <OnboardingFlow onClose={guide.close} />}
    </div>
  );
}
