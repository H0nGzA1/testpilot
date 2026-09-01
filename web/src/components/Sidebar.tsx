import clsx from "clsx";
import {
  Bug,
  ChevronUp,
  FlaskConical,
  GitCompareArrows,
  Layers,
  LayoutDashboard,
  LayoutGrid,
  LogOut,
  MonitorDot,
  PlayCircle,
  Rocket,
  Search,
  Settings as SettingsIcon,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import type { AuthUser, Project } from "../lib/api";
import { setLang } from "../i18n";
import { useAuth } from "../lib/auth";
import { ACCENTS, accentSwatch, getAccent, getTheme, setAccent, setTheme, type Accent, type ThemeMode } from "../lib/theme";

const SECTIONS = [
  { key: "overview", label: "Overview", Icon: LayoutDashboard },
  { key: "cases", label: "Test Cases", Icon: FlaskConical },
  { key: "suites", label: "Suites", Icon: Layers },
  { key: "runs", label: "Runs", Icon: PlayCircle },
  { key: "compare", label: "Compare", Icon: GitCompareArrows },
  { key: "issues", label: "Issues", Icon: Bug },
  { key: "members", label: "Members", Icon: Users },
  { key: "settings", label: "Settings", Icon: SettingsIcon },
] as const;

function Item({
  to,
  active,
  Icon,
  label,
  collapsed,
}: {
  to: string;
  active: boolean;
  Icon: typeof LayoutGrid;
  label: string;
  collapsed: boolean;
}) {
  return (
    <Link
      to={to}
      title={collapsed ? label : undefined}
      className={clsx(
        "flex items-center gap-2.5 rounded-lg py-2 text-sm font-medium transition-colors",
        collapsed ? "justify-center px-0" : "px-2.5",
        active ? "bg-brand-50 text-brand-700" : "text-ink-700 hover:bg-[var(--panel2)]",
      )}
    >
      <Icon className="h-[18px] w-[18px] shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </Link>
  );
}

function AccountMenu({ user, collapsed }: { user: AuthUser; collapsed: boolean }) {
  const { t, i18n } = useTranslation();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [theme, setThemeState] = useState<ThemeMode>(getTheme);
  const [accent, setAccentState] = useState<Accent>(getAccent);
  const ref = useRef<HTMLDivElement>(null);
  const lang = i18n.language;

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const initial = (user.name || user.email).slice(0, 1).toUpperCase();
  const themes: { k: ThemeMode; label: string }[] = [
    { k: "system", label: t("System") },
    { k: "light", label: t("Light") },
    { k: "dark", label: t("Dark") },
  ];
  const seg = (active: boolean) =>
    clsx(
      "flex-1 rounded-md py-1 text-[11px] font-medium transition-colors",
      active ? "bg-brand-50 text-ink-900" : "text-ink-500 hover:text-ink-900",
    );

  return (
    <div ref={ref} className="relative">
      {open && (
        <div
          className={clsx(
            "absolute bottom-full left-0 mb-2 overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-2xl",
            collapsed ? "w-[228px]" : "right-0",
          )}
        >
          <div className="border-b border-[var(--line)] px-3.5 py-3">
            <div className="truncate text-[13px] font-medium text-ink-900">{user.name || user.email}</div>
            <div className="truncate text-[11px] text-ink-500">{user.email}</div>
          </div>
          <div className="px-3.5 pt-3">
            <div className="mb-1.5 text-[11px] text-ink-500">{t("Interface language")}</div>
            <div className="flex gap-1 rounded-lg bg-[var(--panel2)] p-1">
              {(["zh", "en"] as const).map((l) => (
                <button key={l} onClick={() => setLang(l)} className={seg(i18n.language === l)}>
                  {l === "zh" ? "中文" : "EN"}
                </button>
              ))}
            </div>
          </div>
          <div className="px-3.5 pt-3">
            <div className="mb-1.5 text-[11px] text-ink-500">{t("Appearance")}</div>
            <div className="flex gap-1 rounded-lg bg-[var(--panel2)] p-1">
              {themes.map(({ k, label }) => (
                <button
                  key={k}
                  onClick={() => {
                    setTheme(k);
                    setThemeState(k);
                  }}
                  className={seg(theme === k)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="px-3.5 pb-3 pt-3">
            <div className="mb-2 text-[11px] text-ink-500">{lang === "zh" ? "主题色" : "Theme color"}</div>
            <div className="flex items-center gap-2.5">
              {ACCENTS.map((a) => (
                <button
                  key={a.k}
                  title={lang === "zh" ? a.zh : a.en}
                  aria-label={lang === "zh" ? a.zh : a.en}
                  onClick={() => {
                    setAccent(a.k);
                    setAccentState(a.k);
                  }}
                  className={clsx(
                    "h-6 w-6 rounded-full ring-offset-2 ring-offset-[var(--panel)] transition-all",
                    accent === a.k ? "ring-2 ring-ink-900 scale-105" : "ring-1 ring-[var(--line)] hover:scale-110",
                  )}
                  style={{ background: accentSwatch(a.hue) }}
                />
              ))}
            </div>
          </div>
          <button
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
            className="flex w-full items-center gap-2.5 border-t border-[var(--line)] px-3.5 py-2.5 text-left text-[13px] text-[var(--bad-fg)] hover:bg-[var(--panel2)]"
          >
            <LogOut className="h-4 w-4" /> {t("Sign out")}
          </button>
        </div>
      )}
      <button
        onClick={() => setOpen((o) => !o)}
        title={collapsed ? user.name || user.email : undefined}
        className={clsx(
          "flex w-full items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--panel2)] py-2 transition-colors hover:border-brand-100",
          collapsed ? "justify-center px-0" : "px-2.5",
        )}
      >
        <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-600 text-xs font-semibold text-[var(--on-brand)]">
          {initial}
        </div>
        {!collapsed && (
          <>
            <div className="min-w-0 flex-1 text-left">
              <div className="truncate text-[13px] text-ink-700">{user.name || user.email}</div>
              <div className="truncate text-[11px] text-ink-500">{user.is_admin ? t("Admin") : t("Member")}</div>
            </div>
            <ChevronUp className={clsx("h-4 w-4 shrink-0 text-ink-500 transition-transform", open && "rotate-180")} />
          </>
        )}
      </button>
    </div>
  );
}

export function Sidebar({
  projects,
  pid,
  section,
  onSearch,
  collapsed = false,
  onOpenGuide,
}: {
  projects: Project[];
  pid: number | null;
  section: string | null;
  onSearch: () => void;
  collapsed?: boolean;
  /** reopen the guided first-run flow (it only opens by itself once) */
  onOpenGuide?: () => void;
}) {
  const current = projects.find((p) => p.id === pid);
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const { authEnabled, user } = useAuth();
  return (
    <aside
      className={clsx(
        "flex shrink-0 flex-col border-r border-[var(--line)] bg-[var(--panel)] transition-[width] duration-150",
        collapsed ? "w-[60px]" : "w-[212px]",
      )}
    >
      <Link
        to="/"
        className={clsx(
          "flex h-14 items-center gap-2 font-semibold text-ink-900",
          collapsed ? "justify-center px-0" : "px-4",
        )}
      >
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-brand-600 text-[11px] font-bold text-[var(--on-brand)]">
          TP
        </span>
        {!collapsed && (
          <>
            TestPilot
            <span className="text-[11px] font-normal text-ink-500">v0.1</span>
          </>
        )}
      </Link>

      <button
        onClick={onSearch}
        title={collapsed ? `${t("Go to…")} ⌘K` : undefined}
        className={clsx(
          "mb-3 flex items-center gap-2 rounded-lg border border-[var(--line)] py-2 text-sm text-ink-500 hover:border-brand-100",
          collapsed ? "mx-2 justify-center px-0" : "mx-3 px-2.5",
        )}
      >
        <Search className="h-4 w-4 shrink-0" />
        {!collapsed && (
          <>
            {t("Go to…")}
            <span className="ml-auto rounded border border-[var(--line)] px-1 text-[11px]">⌘K</span>
          </>
        )}
      </button>

      <nav className={clsx("flex-1 space-y-0.5", collapsed ? "px-2" : "px-3")}>
        {pid == null ? (
          <>
            <Item to="/" active Icon={LayoutGrid} label={t("Projects")} collapsed={collapsed} />
            {user?.is_admin && (
              <>
                {!collapsed && (
                  <div className="px-2 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                    {t("Admin")}
                  </div>
                )}
                <Item
                  to="/admin/users"
                  active={false}
                  Icon={Users}
                  label={t("Users")}
                  collapsed={collapsed}
                />
                <Item
                  to="/admin/settings"
                  active={false}
                  Icon={ShieldCheck}
                  label={t("System settings")}
                  collapsed={collapsed}
                />
              </>
            )}
          </>
        ) : (
          <>
            {!collapsed && (
              <div className="px-2 pb-1 pt-1 text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                {current?.name ?? `Project #${pid}`}
              </div>
            )}
            {SECTIONS.map(({ key, label, Icon }) => (
              <Item
                key={key}
                to={`/projects/${pid}/${key}`}
                active={section === key}
                Icon={Icon}
                label={t(label)}
                collapsed={collapsed}
              />
            ))}
          </>
        )}
      </nav>

      {onOpenGuide && (
        <div className={clsx("border-t border-[var(--line)]", collapsed ? "p-2" : "px-3 py-2")}>
          <button
            onClick={onOpenGuide}
            title={collapsed ? t("Getting started") : undefined}
            className={clsx(
              "flex w-full items-center gap-2.5 rounded-lg py-2 text-sm font-medium text-ink-500 transition-colors hover:bg-brand-50 hover:text-brand-700",
              collapsed ? "justify-center px-0" : "px-2.5",
            )}
          >
            <Rocket className="h-4 w-4 shrink-0" />
            {!collapsed && <span className="truncate">{t("Getting started")}</span>}
          </button>
        </div>
      )}

      <div className={clsx("border-t border-[var(--line)]", collapsed ? "p-2" : "p-3")}>
        {authEnabled && user ? (
          <AccountMenu user={user} collapsed={collapsed} />
        ) : (
          <>
            {!collapsed && (
              <div className="mb-2 flex items-center gap-1 px-1">
                {(["zh", "en"] as const).map((l) => (
                  <button
                    key={l}
                    onClick={() => setLang(l)}
                    className={clsx(
                      "rounded-md px-2 py-0.5 text-xs font-medium",
                      lang === l ? "bg-brand-50 text-ink-900" : "text-ink-500 hover:bg-[var(--panel2)]",
                    )}
                  >
                    {l === "zh" ? "中" : "EN"}
                  </button>
                ))}
              </div>
            )}
            <div
              title={collapsed ? t("Local instance") : undefined}
              className={clsx(
                "flex items-center gap-2.5 rounded-lg border border-[var(--line)] py-2 text-ink-500",
                collapsed ? "justify-center px-0" : "px-2.5",
              )}
            >
              <MonitorDot className="h-[18px] w-[18px] shrink-0" />
              {!collapsed && (
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-ink-700">{t("Local instance")}</div>
                  <div className="truncate text-[11px] text-ink-500">{t("no sign-in required")}</div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
