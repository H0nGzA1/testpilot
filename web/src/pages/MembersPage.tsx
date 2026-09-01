import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { api, type Member } from "../lib/api";
import { Button, Card, Field, Select } from "../components/ui";
import { useToast } from "../components/toast";
import { useAuth } from "../lib/auth";

const ROLES = ["owner", "editor", "viewer"] as const;
const roleLabel = (r: string) => r.charAt(0).toUpperCase() + r.slice(1);

type Candidate = { id: number; email: string; name: string | null };

export function MembersPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const { sharedWorkspace } = useAuth();
  const pid = Number(useParams().pid);
  const [members, setMembers] = useState<Member[]>([]);
  const [role, setRole] = useState<Member["role"]>("editor");

  // GitLab-style user picker: search existing accounts, pick one (no free-text add)
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const load = () => api.listMembers(pid).then(setMembers).catch((e) => toast("error", String(e)));
  useEffect(() => {
    if (!sharedWorkspace) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid, sharedWorkspace]);

  // debounced search whenever the dropdown is open
  useEffect(() => {
    if (!open) return;
    const id = setTimeout(() => {
      api
        .assignableUsers(pid, query)
        .then(setResults)
        .catch(() => setResults([]));
    }, 180);
    return () => clearTimeout(id);
  }, [query, open, pid]);

  // close on outside click
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const pick = (c: Candidate) => {
    setSelected(c);
    setQuery(c.email);
    setOpen(false);
  };

  const add = async () => {
    if (!selected) return;
    setAdding(true);
    try {
      await api.addMember(pid, { email: selected.email, role });
      setSelected(null);
      setQuery("");
      setResults([]);
      load();
    } catch (e) {
      toast("error", String(e));
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-900">{t("Members")}</h1>
        <p className="mt-1 text-sm text-ink-500">{t("Who can access this project, and at what level.")}</p>
      </div>

      {sharedWorkspace ? (
        <Card className="space-y-2 p-4">
          <div className="text-sm font-medium text-ink-900">{t("Shared workspace")}</div>
          <p className="text-sm text-ink-500">
            {t(
              "Every signed-in user can access all projects — no need to add members here. Manage accounts under Users.",
            )}
          </p>
        </Card>
      ) : (
        <>
          <Card className="space-y-3 p-4">
            <div className="text-sm font-medium text-ink-900">{t("Add member")}</div>
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[18rem] flex-1">
                <Field label={t("Search users by email or name")}>
                  <div ref={boxRef} className="relative">
                    <input
                      value={query}
                      onChange={(e) => {
                        setQuery(e.target.value);
                        setSelected(null);
                        setOpen(true);
                      }}
                      onFocus={() => setOpen(true)}
                      placeholder={t("Type to search accounts…")}
                      className="h-10 w-full rounded-lg border border-[var(--line)] bg-[var(--panel)] px-3 text-sm text-ink-900 outline-none transition-colors focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
                    />
                    {open && (
                      <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-[var(--line)] bg-[var(--panel)] py-1 shadow-2xl">
                        {results.length === 0 ? (
                          <div className="px-3 py-2 text-xs text-ink-500">{t("No matching users")}</div>
                        ) : (
                          results.map((u) => (
                            <button
                              key={u.id}
                              type="button"
                              onClick={() => pick(u)}
                              className="flex w-full flex-col items-start px-3 py-1.5 text-left hover:bg-brand-50"
                            >
                              <span className="text-sm text-ink-900">{u.email}</span>
                              {u.name && <span className="text-[11px] text-ink-500">{u.name}</span>}
                            </button>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                </Field>
              </div>
              <Field label={t("Role")}>
                <Select value={role} onChange={(e) => setRole(e.target.value as Member["role"])}>
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(roleLabel(r))}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button onClick={add} disabled={!selected || adding}>
                {t("Add")}
              </Button>
            </div>
            <p className="text-xs text-ink-500">{t("No account yet? Invite them under Users first.")}</p>
          </Card>

          <Card>
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--line)] text-left text-xs text-ink-500">
                <tr>
                  <th className="px-4 py-2">{t("Email")}</th>
                  <th className="px-4 py-2">{t("Name")}</th>
                  <th className="px-4 py-2">{t("Role")}</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.user_id} className="border-b border-[var(--line)] last:border-0">
                    <td className="px-4 py-2 text-ink-900">{m.email}</td>
                    <td className="px-4 py-2 text-ink-700">{m.name ?? "—"}</td>
                    <td className="px-4 py-2">
                      <Select
                        value={m.role}
                        className="h-8 w-auto"
                        onChange={(e) =>
                          api
                            .updateMember(pid, m.user_id, e.target.value)
                            .then(load)
                            .catch((err) => toast("error", String(err)))
                        }
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {t(roleLabel(r))}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() =>
                          api.removeMember(pid, m.user_id).then(load).catch((e) => toast("error", String(e)))
                        }
                      >
                        {t("Remove")}
                      </Button>
                    </td>
                  </tr>
                ))}
                {members.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-ink-500">
                      {t("No members yet.")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}
