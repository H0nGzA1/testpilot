import i18n from "../i18n";

export interface Project {
  id: number;
  name: string;
  base_url: string | null;
  has_login_state: boolean;
  roles?: string[];
  gitlab_project?: string | null;
  case_timeout_s?: number | null;
  case_max_steps?: number | null;
  run_concurrency?: number | null;
  feishu_chat_id?: string | null;
  feishu_bitable_bound?: boolean;
  case_count?: number;
  last_run?: {
    id: number;
    status: string;
    pass_rate: number | null;
    finished_at: string | null;
  } | null;
}

export interface ProjectStats {
  base_url: string | null;
  has_credential: boolean;
  has_healthy_credential: boolean;
  issue_count: number;
  case_count: number;
  enabled_count: number;
  run_count: number;
  last_run: Run | null;
  trend: { run_id: number; name: string; pass_rate: number; finished_at: string | null }[];
  last_pass_rate: number | null;
  last_latency_p50_ms: number | null;
  last_flaky: number;
  top_failing: { case_id: number; name: string; fail_count: number }[];
}

export interface Environment {
  id: number;
  project_id: number;
  name: string;
  base_url: string | null;
  is_default: boolean;
}

export interface Credential {
  id: number;
  project_id: number;
  type: "storage_state" | "password";
  role: string | null;
  environment_id: number | null;
  label: string;
  username: string | null;
  is_active: boolean;
  healthy: boolean;
  last_error: string | null;
  last_checked_at: string | null;
  expires_at: string | null;
  created_at: string | null;
}

export type IssueStatus = "open" | "in_progress" | "fixed" | "verified" | "closed";
export type Severity = "low" | "medium" | "high" | "critical";

export interface IssueComment {
  id: number;
  issue_id: number;
  body: string;
  author: string | null;
  created_at: string | null;
}

export interface Issue {
  id: number;
  project_id: number;
  title: string;
  description: string;
  status: IssueStatus;
  severity: Severity;
  assignee: string | null;
  labels: string[];
  case_id: number | null;
  run_id: number | null;
  result_id: number | null;
  gitlab_iid?: number | null;
  gitlab_url?: string | null;
  created_at: string | null;
  updated_at: string | null;
  comments?: IssueComment[];
}

export type FeedbackCategory = "bug" | "question" | "feature" | "other";

export interface FeedbackItem {
  id: number;
  source: string;
  chat_id: string | null;
  chat_type: string | null;
  sender_id: string | null;
  sender_name: string | null;
  content: string;
  title: string | null;
  category: FeedbackCategory;
  severity: Severity;
  answer: string | null;
  answered: boolean;
  status: string;
  project_id: number | null;
  issue_id: number | null;
  created_at: string | null;
}

export interface LlmStatus {
  base_url: string;
  model: string;
  agent_model: string;
  api_key_set: boolean;
}

export interface LlmSettingsIn {
  base_url?: string; // "" clears the override (falls back to env)
  model?: string;
  agent_model?: string;
  api_key?: string; // blank keeps the stored key
}

export interface FeishuStatus {
  app_id: string;
  app_secret_set: boolean;
  verification_token_set: boolean;
  api_base: string;
  auto_answer_detected: boolean;
}

export interface FeishuSettingsIn {
  app_id?: string;
  api_base?: string;
  auto_answer_detected?: boolean;
  app_secret?: string; // blank keeps the stored value
  verification_token?: string; // blank keeps the stored value
}

export interface GitLabConfig {
  gitlab_project: string | null;
  has_token: boolean;
  token_source?: "project" | "global" | null;
  sync_enabled: boolean;
}

export interface CaseResult {
  result_id: number;
  run_id: number;
  run_name: string;
  status: "passed" | "failed" | "error";
  flaky: boolean;
  latency_ms: number;
  judge_reason: string | null;
  video_url: string | null;
  trace_url: string | null;
  finished_at: string | null;
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const t = i18n.t.bind(i18n);
  if (s < 60) return t("just now");
  if (s < 3600) return t("{{n}}m ago", { n: Math.floor(s / 60) });
  if (s < 86400) return t("{{n}}h ago", { n: Math.floor(s / 3600) });
  return t("{{n}}d ago", { n: Math.floor(s / 86400) });
}

export type CasePriority = "P0" | "P1" | "P2" | "P3";
export type CaseType = "functional" | "smoke" | "regression" | "acceptance" | "negative";
export type CaseStatus = "draft" | "active" | "deprecated";

export interface TestStep {
  action: string;
  expected: string;
}

export interface TestCase {
  id: number;
  project_id: number;
  case_key: string | null;
  name: string;
  module: string | null;
  priority: CasePriority;
  type: CaseType;
  status: CaseStatus;
  owner: string | null;
  role: string | null;
  references: string;
  preconditions: string;
  prompt: string;
  steps: TestStep[];
  test_data: string;
  expected: string;
  start_url: string | null;
  tags: string[];
  enabled: boolean;
  updated_at?: string | null;
  last_status?: "passed" | "failed" | "error" | null; // latest run result; null = never run
  last_run_id?: number | null; // the run that verdict came from
  last_run_at?: string | null; // when it last ran
}

export interface RunSummary {
  total: number;
  passed: number;
  failed: number;
  error: number;
  flaky: number;
  pass_rate: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
}

export interface Run {
  id: number;
  project_id: number;
  name: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  concurrency: number;
  case_ids: number[];
  total_count: number;
  processed_count: number;
  passed_count: number;
  summary: RunSummary | null;
  started_at: string | null;
  finished_at: string | null;
  created_at?: string | null;
  created_by?: string | null;
  suite_id?: number | null;
  ran_by_user_id?: number | null;
  ran_by_label?: string | null;
  trigger?: "manual" | "suite";
  environment_id?: number | null;
}

export type Cadence = "none" | "daily" | "weekly" | "biweekly" | "monthly";

export interface Suite {
  id: number;
  project_id: number;
  name: string;
  description: string;
  selection_mode: "cases" | "tags";
  case_ids: number[];
  tag_filter: string[];
  owner_user_id: number | null;
  owner_label: string | null;
  runner_user_id: number | null;
  runner_label: string | null;
  environment_id: number | null;
  cadence: Cadence;
  due_at: string | null;
  last_run_id: number | null;
  last_status: string | null;
  last_run_at: string | null;
  created_at?: string | null;
}

export interface AppNotification {
  id: number;
  type: string;
  title: string;
  body: string;
  link: string | null;
  suite_id: number | null;
  run_id: number | null;
  issue_id: number | null;
  read: boolean;
  created_at: string | null;
}

export interface RunResult {
  id: number;
  run_id: number;
  case_id: number;
  status: "passed" | "failed" | "error" | "running";
  attempts: number;
  flaky: boolean;
  video_url: string | null;
  trace_url: string | null;
  steps: string[];
  diagnostics?: DiagStep[];
  judge_reason: string | null;
  final_answer: string | null;
  account_label?: string | null;
  latency_ms: number;
  error: string | null;
}

export interface DiagStep {
  i: number;
  action: string;
  thought: string;
  result: string;
  error: string;
  screenshot: string | null;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listProjects: () => req<Project[]>("/projects"),
  createProject: (b: { name: string; base_url?: string; login_state?: string }) =>
    req<Project>("/projects", { method: "POST", body: JSON.stringify(b) }),
  updateProject: (
    pid: number,
    b: {
      name?: string;
      base_url?: string;
      case_timeout_s?: number | null;
      case_max_steps?: number | null;
      run_concurrency?: number | null;
      feishu_chat_id?: string | null;
      feishu_bitable_url?: string | null;
    },
  ) =>
    req<Project>(`/projects/${pid}`, { method: "PUT", body: JSON.stringify(b) }),
  deleteProject: (pid: number) =>
    req<{ deleted: number }>(`/projects/${pid}`, { method: "DELETE" }),
  getRoles: (pid: number) => req<{ roles: string[] }>(`/projects/${pid}/roles`),
  setRoles: (pid: number, roles: string[]) =>
    req<{ roles: string[] }>(`/projects/${pid}/roles`, { method: "PUT", body: JSON.stringify({ roles }) }),

  // environments
  listEnvironments: (pid: number) => req<Environment[]>(`/projects/${pid}/environments`),
  createEnvironment: (pid: number, b: { name: string; base_url?: string; is_default?: boolean }) =>
    req<Environment>(`/projects/${pid}/environments`, { method: "POST", body: JSON.stringify(b) }),
  updateEnvironment: (eid: number, b: Record<string, unknown>) =>
    req<Environment>(`/environments/${eid}`, { method: "PUT", body: JSON.stringify(b) }),
  deleteEnvironment: (eid: number) =>
    req<{ deleted: number }>(`/environments/${eid}`, { method: "DELETE" }),

  getGitlabConfig: (pid: number) => req<GitLabConfig>(`/projects/${pid}/gitlab`),
  listGitlabProjects: (pid: number) =>
    req<{ id: number; path: string; name: string | null }[]>(`/projects/${pid}/gitlab/projects`),
  setGitlabConfig: (pid: number, b: { gitlab_project: string; token?: string }) =>
    req<GitLabConfig>(`/projects/${pid}/gitlab`, { method: "PUT", body: JSON.stringify(b) }),

  listCredentials: (pid: number) => req<Credential[]>(`/projects/${pid}/credentials`),
  createCredential: (
    pid: number,
    b: {
      type: "storage_state" | "password";
      role?: string | null;
      environment_id?: number | null;
      label?: string;
      username?: string;
      secret: string;
    },
  ) => req<Credential>(`/projects/${pid}/credentials`, { method: "POST", body: JSON.stringify(b) }),
  captureCredential: (pid: number, b: { label?: string; username: string; password: string }) =>
    req<Credential>(`/projects/${pid}/credentials/capture`, { method: "POST", body: JSON.stringify(b) }),
  activateCredential: (cid: number) =>
    req<Credential>(`/credentials/${cid}/activate`, { method: "POST" }),
  recheckCredential: (cid: number) =>
    req<Credential>(`/credentials/${cid}/recheck`, { method: "POST" }),
  deleteCredential: (cid: number) =>
    req<{ deleted: number }>(`/credentials/${cid}`, { method: "DELETE" }),

  listCases: (pid: number) => req<TestCase[]>(`/projects/${pid}/testcases`),
  createCase: (pid: number, b: Partial<TestCase>) =>
    req<TestCase>(`/projects/${pid}/testcases`, { method: "POST", body: JSON.stringify(b) }),
  updateCase: (id: number, b: Partial<TestCase>) =>
    req<TestCase>(`/testcases/${id}`, { method: "PUT", body: JSON.stringify(b) }),
  deleteCase: (id: number) => req<{ deleted: number }>(`/testcases/${id}`, { method: "DELETE" }),
  importCasesXlsx: async (pid: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/projects/${pid}/testcases/import`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json() as Promise<{ imported: number }>;
  },
  exportUrl: (pid: number) => `/api/projects/${pid}/testcases/export`,
  templateUrl: (pid: number) => `/api/projects/${pid}/testcases/template`,

  getStats: (pid: number) => req<ProjectStats>(`/projects/${pid}/stats`),
  getCaseResults: (cid: number) => req<CaseResult[]>(`/testcases/${cid}/results`),

  createRun: (pid: number, b: { name?: string; case_ids?: number[]; tags?: string[]; concurrency?: number }) =>
    req<Run>(`/projects/${pid}/runs`, { method: "POST", body: JSON.stringify(b) }),
  listRuns: (pid: number) => req<Run[]>(`/projects/${pid}/runs`),
  getRun: (rid: number) => req<Run>(`/runs/${rid}`),

  // suites
  listSuites: (pid: number) => req<Suite[]>(`/projects/${pid}/suites`),
  createSuite: (
    pid: number,
    b: {
      name: string;
      description?: string;
      selection_mode?: "cases" | "tags";
      case_ids?: number[];
      tag_filter?: string[];
      owner_user_id?: number | null;
      runner_user_id?: number | null;
      cadence?: Cadence;
    },
  ) => req<Suite>(`/projects/${pid}/suites`, { method: "POST", body: JSON.stringify(b) }),
  updateSuite: (sid: number, b: Record<string, unknown>) =>
    req<Suite>(`/suites/${sid}`, { method: "PUT", body: JSON.stringify(b) }),
  deleteSuite: (sid: number) => req<{ deleted: number }>(`/suites/${sid}`, { method: "DELETE" }),
  assignSuite: (sid: number, runner_user_id: number | null) =>
    req<Suite>(`/suites/${sid}/assign`, {
      method: "POST",
      body: JSON.stringify({ runner_user_id }),
    }),
  runSuite: (sid: number) => req<Run>(`/suites/${sid}/run`, { method: "POST" }),

  // notifications
  listNotifications: () => req<AppNotification[]>("/notifications"),
  unreadCount: () => req<{ count: number }>("/notifications/unread-count"),
  readNotification: (nid: number) =>
    req<{ ok: boolean }>(`/notifications/${nid}/read`, { method: "POST" }),
  readAllNotifications: () =>
    req<{ ok: boolean }>("/notifications/read-all", { method: "POST" }),
  getResults: (rid: number) => req<RunResult[]>(`/runs/${rid}/results`),
  cancelRun: (rid: number) => req<Run>(`/runs/${rid}/cancel`, { method: "POST" }),
  // undefined = every case; "failing" = everything that didn't pass; "error" = infra
  // outcomes only (timeouts, dead sessions) — a judge failure is a product finding.
  rerun: (rid: number, only?: "failing" | "error") =>
    req<Run>(`/runs/${rid}/rerun${only ? `?only=${only}` : ""}`, { method: "POST" }),
  renameRun: (rid: number, name: string) =>
    req<Run>(`/runs/${rid}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteRun: (rid: number) => req<{ deleted: number }>(`/runs/${rid}`, { method: "DELETE" }),
  runExportUrl: (rid: number) => `/api/runs/${rid}/export`,

  listIssues: (pid: number) => req<Issue[]>(`/projects/${pid}/issues`),
  createIssue: (pid: number, b: Partial<Issue>) =>
    req<Issue>(`/projects/${pid}/issues`, { method: "POST", body: JSON.stringify(b) }),
  getIssue: (iid: number) => req<Issue>(`/issues/${iid}`),
  updateIssue: (iid: number, b: Partial<Issue>) =>
    req<Issue>(`/issues/${iid}`, { method: "PUT", body: JSON.stringify(b) }),
  deleteIssue: (iid: number) => req<{ deleted: number }>(`/issues/${iid}`, { method: "DELETE" }),
  addComment: (iid: number, b: { body: string; author?: string }) =>
    req<IssueComment>(`/issues/${iid}/comments`, { method: "POST", body: JSON.stringify(b) }),
  listProjectFeedback: (pid: number, q?: { status?: string; category?: string }) => {
    const s = new URLSearchParams();
    if (q?.status) s.set("status", q.status);
    if (q?.category) s.set("category", q.category);
    const qs = s.toString();
    return req<FeedbackItem[]>(`/projects/${pid}/feedback${qs ? `?${qs}` : ""}`);
  },
  promoteFeedback: (fid: number) =>
    req<Issue>(`/feedback/${fid}/promote`, { method: "POST" }),

  streamUrl: (rid: number) => `/api/runs/${rid}/stream`,

  // --- auth ---
  config: () =>
    req<{
      auth_enabled: boolean;
      shared_workspace: boolean;
      public_base_url: string;
      gitlab_enabled: boolean;
      feishu_enabled: boolean;
    }>("/config"),
  me: () => req<AuthUser | null>("/auth/me"),
  login: (email: string, password: string) =>
    req<AuthUser>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => req<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  setOnboarded: () =>
    req<{ onboarded_at: string | null }>("/auth/onboarded", { method: "POST" }),
  getInvite: (token: string) =>
    req<{ email: string; is_admin: boolean; project_id: number | null }>(`/invite/${token}`),
  acceptInvite: (token: string, b: { name: string; password: string }) =>
    req<AuthUser>(`/invite/${token}/accept`, { method: "POST", body: JSON.stringify(b) }),

  // --- admin ---
  listUsers: () => req<AdminUser[]>("/admin/users"),
  inviteUser: (b: { email: string; is_admin?: boolean; project_id?: number; project_role?: string }) =>
    req<{ email: string; link: string; emailed: boolean }>("/admin/users/invite", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  updateUser: (uid: number, b: { is_active?: boolean; is_admin?: boolean }) =>
    req<AdminUser>(`/admin/users/${uid}`, { method: "PATCH", body: JSON.stringify(b) }),
  getAdminSettings: () =>
    req<{ llm: LlmStatus; gitlab_token_set: boolean; feishu: FeishuStatus }>("/admin/settings"),
  setGitlabToken: (token: string) =>
    req<{ gitlab_token_set: boolean }>("/admin/settings/gitlab-token", {
      method: "PUT",
      body: JSON.stringify({ token }),
    }),
  setLlmSettings: (b: LlmSettingsIn) =>
    req<LlmStatus>("/admin/settings/llm", { method: "PUT", body: JSON.stringify(b) }),
  setFeishuSettings: (b: FeishuSettingsIn) =>
    req<FeishuStatus>("/admin/settings/feishu", { method: "PUT", body: JSON.stringify(b) }),

  // --- project members ---
  listMembers: (pid: number) => req<Member[]>(`/projects/${pid}/members`),
  assignableUsers: (pid: number, q: string) =>
    req<{ id: number; email: string; name: string | null }[]>(
      `/projects/${pid}/assignable-users?q=${encodeURIComponent(q)}`,
    ),
  addMember: (pid: number, b: { email: string; role: string }) =>
    req<Member>(`/projects/${pid}/members`, { method: "POST", body: JSON.stringify(b) }),
  updateMember: (pid: number, uid: number, role: string) =>
    req<Member>(`/projects/${pid}/members/${uid}`, { method: "PATCH", body: JSON.stringify({ role }) }),
  removeMember: (pid: number, uid: number) =>
    req<{ removed: number }>(`/projects/${pid}/members/${uid}`, { method: "DELETE" }),
};

export interface AuthUser {
  id: number;
  email: string;
  name: string | null;
  is_admin: boolean;
  /** null = has never finished or dismissed the guided first-run flow */
  onboarded_at: string | null;
}
export interface AdminUser extends AuthUser {
  is_active: boolean;
  last_login_at?: string | null;
}
export interface Member {
  user_id: number;
  email: string;
  name: string | null;
  role: "owner" | "editor" | "viewer";
}
