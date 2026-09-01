import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type AdminUser, type Project } from "../lib/api";
import { Badge, Button, Card, Checkbox, Field, Input, Select } from "../components/ui";
import { useToast } from "../components/toast";

const ROLES = ["owner", "editor", "viewer"] as const;
const roleLabel = (r: string) => r.charAt(0).toUpperCase() + r.slice(1);

export function AdminUsersPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [email, setEmail] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [projectId, setProjectId] = useState("");
  const [role, setRole] = useState<(typeof ROLES)[number]>("editor");
  const [lastLink, setLastLink] = useState("");

  const load = () => api.listUsers().then(setUsers).catch((e) => toast("error", String(e)));
  useEffect(() => {
    load();
    api.listProjects().then(setProjects).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const invite = async () => {
    if (!email.trim()) return;
    try {
      const r = await api.inviteUser({
        email: email.trim(),
        is_admin: isAdmin,
        project_id: projectId ? Number(projectId) : undefined,
        project_role: role,
      });
      setLastLink(new URL(r.link, window.location.origin).href);
      setEmail("");
      setIsAdmin(false);
      setProjectId("");
      setRole("editor");
      toast("success", r.emailed ? t("Invite emailed to {{e}}", { e: r.email }) : t("Invite created — copy the link below"));
    } catch (e) {
      toast("error", String(e));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">{t("Users")}</h1>
        <p className="mt-1 text-sm text-ink-500">{t("Invite testers and manage accounts.")}</p>
      </div>

      <Card className="space-y-3 p-4">
        <div className="text-sm font-medium text-ink-900">{t("Invite a user")}</div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[16rem] flex-1">
            <Field label={t("Email")}>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="tester@example.com" />
            </Field>
          </div>
          <Field label={t("Assign to project (optional)")}>
            <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">{t("— none —")}</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </Select>
          </Field>
          <Field label={t("Role")}>
            <Select value={role} onChange={(e) => setRole(e.target.value as (typeof ROLES)[number])} disabled={!projectId}>
              {ROLES.map((r) => (
                <option key={r} value={r}>{t(roleLabel(r))}</option>
              ))}
            </Select>
          </Field>
          <label className="flex items-center gap-2 pb-2 text-sm text-ink-700">
            <Checkbox checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
            {t("System admin")}
          </label>
          <Button onClick={invite}>{t("Send invite")}</Button>
        </div>
        {lastLink && (
          <div className="rounded-lg bg-[var(--panel2)] px-3 py-2 text-xs text-ink-700">
            {t("Invite link:")}{" "}
            <a href={lastLink} className="break-all text-brand-700 hover:underline">{lastLink}</a>
          </div>
        )}
      </Card>

      <Card>
        <table className="w-full text-sm">
          <thead className="border-b border-[var(--line)] text-left text-xs text-ink-500">
            <tr>
              <th className="px-4 py-2">{t("Email")}</th>
              <th className="px-4 py-2">{t("Name")}</th>
              <th className="px-4 py-2">{t("Role")}</th>
              <th className="px-4 py-2">{t("Status")}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-[var(--line)] last:border-0">
                <td className="px-4 py-2 text-ink-900">{u.email}</td>
                <td className="px-4 py-2 text-ink-700">{u.name ?? "—"}</td>
                <td className="px-4 py-2">
                  {u.is_admin ? <Badge status="running">{t("Admin")}</Badge> : <span className="text-ink-500">{t("Member")}</span>}
                </td>
                <td className="px-4 py-2">
                  {u.is_active ? <Badge status="passed">{t("Active")}</Badge> : <Badge status="cancelled">{t("Disabled")}</Badge>}
                </td>
                <td className="px-4 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="sm" variant="outline"
                      onClick={() => api.updateUser(u.id, { is_admin: !u.is_admin }).then(load).catch((e) => toast("error", String(e)))}>
                      {u.is_admin ? t("Revoke admin") : t("Make admin")}
                    </Button>
                    <Button size="sm" variant={u.is_active ? "danger" : "outline"}
                      onClick={() => api.updateUser(u.id, { is_active: !u.is_active }).then(load).catch((e) => toast("error", String(e)))}>
                      {u.is_active ? t("Disable") : t("Enable")}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
