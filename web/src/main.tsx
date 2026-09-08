import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import "./index.css";
import "./i18n";
import { initTheme } from "./lib/theme";
import { AuthProvider, useAuth } from "./lib/auth";
import { Layout } from "./components/Layout";
import { ToastProvider } from "./components/toast";
import { AdminSettingsPage } from "./pages/AdminSettingsPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { CasesPage } from "./pages/CasesPage";
import { ComparePage } from "./pages/ComparePage";
import { InvitePage } from "./pages/InvitePage";
import { IssuesPage } from "./pages/IssuesPage";
import { LoginPage } from "./pages/LoginPage";
import { MembersPage } from "./pages/MembersPage";
import { OverviewPage } from "./pages/OverviewPage";
import { Projects } from "./pages/Projects";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { RunReport } from "./pages/RunReport";
import { RunsPage } from "./pages/RunsPage";
import { SuitesPage } from "./pages/SuitesPage";
import { SettingsPage } from "./pages/SettingsPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { loading, authEnabled, user } = useAuth();
  if (loading) return null;
  if (authEnabled && !user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { loading, authEnabled, user } = useAuth();
  if (loading) return null;
  if (authEnabled && !user) return <Navigate to="/login" replace />;
  if (authEnabled && user && !user.is_admin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/invite/:token", element: <InvitePage /> },
  { path: "/reset/:token", element: <ResetPasswordPage /> },
  {
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { path: "/", element: <Projects /> },
      { path: "/admin/users", element: <RequireAdmin><AdminUsersPage /></RequireAdmin> },
      { path: "/admin/settings", element: <RequireAdmin><AdminSettingsPage /></RequireAdmin> },
      { path: "/projects/:pid", element: <Navigate to="overview" replace /> },
      { path: "/projects/:pid/overview", element: <OverviewPage /> },
      { path: "/projects/:pid/cases", element: <CasesPage /> },
      { path: "/projects/:pid/suites", element: <SuitesPage /> },
      { path: "/projects/:pid/runs", element: <RunsPage /> },
      { path: "/projects/:pid/runs/:rid", element: <RunReport /> },
      { path: "/projects/:pid/compare", element: <ComparePage /> },
      { path: "/projects/:pid/issues", element: <IssuesPage /> },
      { path: "/projects/:pid/members", element: <MembersPage /> },
      { path: "/projects/:pid/settings", element: <SettingsPage /> },
    ],
  },
]);

initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </AuthProvider>
  </React.StrictMode>,
);
