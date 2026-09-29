import type {
  AuditEventDetail,
  AuditEventSummary,
  ContentRunCounts,
  ContentRunDetail,
  ContentRunSummary,
  CreateMemberCommand,
  CreateMemberResult,
  CreateModelCredentialCommand,
  ExportSummary,
  HumanTaskCounts,
  HumanTaskSummary,
  MaterialSummary,
  MemberSummary,
  ModelCatalogItem,
  ModelCredentialSummary,
  ModelProviderSummary,
  ModelRoutePolicyCreateRequest,
  ModelRoutePolicyDetail,
  ModelRoutePolicySummary,
  PermissionItem,
  QuotaOverview,
  QuotaPolicyDetail,
  ResetMemberPasswordResult,
  RoleDetail,
  RoleSummary,
  TenantSession,
  WorkflowTemplateDetail,
  WorkflowTemplateSummary,
} from "@/lib/types";

export interface Page<T> { items: T[]; page: number; page_size: number; total: number; }
export interface LoginCommand { email: string; password: string; }
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  instance?: string;
  request_id?: string;
  errors?: Array<{ field?: string; message: string }>;
  meta?: Record<string, unknown>;
}

export class ApiProblem extends Error {
  constructor(public readonly problem: ProblemDetails) {
    super(problem.detail || problem.title);
  }
}

export interface ActionCommand {
  action: string;
  assigneeId?: string;
}

export interface ContentRunCreate {
  title: string;
  brand: string;
  stageLabel?: string;
}

export interface MaterialCreate {
  title?: string;
  url?: string;
  summary?: string;
  trustLabel?: string;
}

export interface ListQuery {
  page?: number;
  pageSize?: number;
  q?: string;
  status?: string;
  type?: string;
  mine?: boolean;
  action?: string;
  result?: string;
}

export interface ApiClient {
  login(command: LoginCommand): Promise<TenantSession>;
  logout(): Promise<void>;
  refresh(): Promise<boolean>;
  getSession(): Promise<TenantSession>;
  listContentRuns(query?: ListQuery): Promise<Page<ContentRunSummary>>;
  contentRunCounts(): Promise<ContentRunCounts>;
  getContentRun(id: string): Promise<ContentRunDetail>;
  createContentRun(command: ContentRunCreate): Promise<ContentRunSummary>;
  runContentAction(id: string, command: ActionCommand, etag: string): Promise<ContentRunSummary>;
  listContentExports(id: string): Promise<ExportSummary[]>;
  downloadExport(id: string, exportId: string, fallbackName: string): Promise<void>;
  attachMaterial(runId: string, materialId: string): Promise<ContentRunSummary>;
  listHumanTasks(query?: ListQuery): Promise<Page<HumanTaskSummary>>;
  humanTaskCounts(): Promise<HumanTaskCounts>;
  runHumanTaskAction(id: string, command: ActionCommand, etag: string): Promise<HumanTaskSummary>;
  listMaterials(query?: ListQuery): Promise<Page<MaterialSummary>>;
  createMaterial(command: MaterialCreate): Promise<MaterialSummary>;
  uploadMaterial(file: File, title: string, trustLabel: string): Promise<MaterialSummary>;
  downloadMaterial(id: string, fallbackName: string): Promise<void>;
  listMembers(query?: ListQuery): Promise<Page<MemberSummary>>;
  listOrganizationMembers(): Promise<MemberSummary[]>;
  getMember(id: string): Promise<MemberSummary>;
  createMember(command: CreateMemberCommand): Promise<CreateMemberResult>;
  updateMember(id: string, data: { role_id?: string; status?: string }): Promise<MemberSummary>;
  resetMemberPassword(id: string): Promise<ResetMemberPasswordResult>;
  listRoles(): Promise<RoleSummary[]>;
  getRole(id: string): Promise<RoleDetail>;
  updateRole(id: string, data: { name?: string; description?: string; permissions?: PermissionItem[] }): Promise<RoleDetail>;
  listWorkflowTemplates(query?: ListQuery): Promise<Page<WorkflowTemplateSummary>>;
  getWorkflowTemplate(id: string): Promise<WorkflowTemplateDetail>;
  publishWorkflowTemplate(id: string): Promise<WorkflowTemplateDetail>;
  listAuditLogs(query?: ListQuery): Promise<Page<AuditEventSummary>>;
  getAuditLog(id: string): Promise<AuditEventDetail>;
  listModelProviders(): Promise<ModelProviderSummary[]>;
  listModelCatalog(): Promise<ModelCatalogItem[]>;
  listModelCredentials(query?: ListQuery): Promise<Page<ModelCredentialSummary>>;
  createModelCredential(command: CreateModelCredentialCommand): Promise<ModelCredentialSummary>;
  testModelCredential(id: string): Promise<ModelCredentialSummary>;
  revokeModelCredential(id: string): Promise<void>;
  listModelRoutePolicies(): Promise<ModelRoutePolicySummary[]>;
  getModelRoutePolicy(taskType: string): Promise<ModelRoutePolicyDetail>;
  upsertModelRoutePolicy(taskType: string, data: ModelRoutePolicyCreateRequest): Promise<ModelRoutePolicyDetail>;
  listQuotaPolicies(): Promise<QuotaPolicyDetail[]>;
  getQuotaPolicy(id: string): Promise<QuotaPolicyDetail>;
  getQuotaOverview(): Promise<QuotaOverview>;
  upsertQuotaPolicy(metric: string, data: { period_type: "DAILY" | "MONTHLY" | "ROLLING_30D"; soft_limit: number | null; hard_limit: number | null; overage_allowed: boolean; status: "ACTIVE" | "DISABLED"; }): Promise<QuotaPolicyDetail>;
}

/** Read a filename out of Content-Disposition, preferring the RFC 5987 form. */
function filenameFrom(header: string | null): string | null {
  if (!header) return null;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      return encoded[1];
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1] : null;
}

function toQueryString(query: ListQuery): string {
  const params = new URLSearchParams();
  if (query.page) params.set("page", String(query.page));
  if (query.pageSize) params.set("page_size", String(query.pageSize));
  if (query.q?.trim()) params.set("q", query.q.trim());
  if (query.status) params.set("status", query.status);
  if (query.type) params.set("type", query.type);
  if (query.mine) params.set("mine", "true");
  if (query.action) params.set("action", query.action);
  if (query.result) params.set("result", query.result);
  return params.toString();
}

/** Hand a fetched blob to the browser as a download. */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export class HttpApiClient implements ApiClient {
  constructor(private readonly baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1") {}

  private async request<T>(path: string, init?: RequestInit, allowRefresh = true): Promise<T> {
    const headers = new Headers(init?.headers);
    if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });

    // Access tokens are short-lived. On 401, try one silent refresh and replay
    // the original request; only give up if the refresh itself fails.
    if (response.status === 401 && allowRefresh && path !== "/auth/refresh") {
      if (await this.refresh()) return this.request<T>(path, init, false);
    }
    if (!response.ok) throw new ApiProblem(await response.json() as ProblemDetails);
    // 204 (logout) and other empty bodies have nothing to parse.
    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as T;
    }
    return response.json() as Promise<T>;
  }

  private async download(path: string, fallbackName: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}${path}`, { credentials: "include" });
    if (response.status === 401 && await this.refresh()) {
      return this.download(path, fallbackName);
    }
    if (!response.ok) throw new ApiProblem(await response.json() as ProblemDetails);
    saveBlob(await response.blob(), filenameFrom(response.headers.get("content-disposition")) ?? fallbackName);
  }

  login(command: LoginCommand) { return this.request<TenantSession>("/auth/login", { method: "POST", body: JSON.stringify(command) }); }
  logout() { return this.request<void>("/auth/logout", { method: "POST" }, false); }
  async refresh(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      return response.ok;
    } catch {
      return false;
    }
  }
  getSession() { return this.request<TenantSession>("/me"); }
  listContentRuns(query: ListQuery = {}) { return this.request<Page<ContentRunSummary>>(`/workflow-runs?${toQueryString(query)}`); }
  contentRunCounts() { return this.request<ContentRunCounts>("/workflow-runs/counts"); }
  getContentRun(id: string) { return this.request<ContentRunDetail>(`/workflow-runs/${id}`); }
  createContentRun(command: ContentRunCreate) {
    return this.request<ContentRunSummary>("/workflow-runs", { method: "POST", body: JSON.stringify(command) });
  }
  // If-Match carries the version the UI rendered; a mismatch means somebody else
  // changed the row and the caller must re-read before deciding again.
  runContentAction(id: string, command: ActionCommand, etag: string) {
    return this.request<ContentRunSummary>(`/workflow-runs/${id}/actions`, {
      method: "POST",
      body: JSON.stringify(command),
      headers: { "If-Match": etag },
    });
  }
  listContentExports(id: string) { return this.request<ExportSummary[]>(`/workflow-runs/${id}/exports`); }
  downloadExport(id: string, exportId: string, fallbackName: string) {
    return this.download(`/workflow-runs/${id}/exports/${exportId}/download`, fallbackName);
  }
  attachMaterial(runId: string, materialId: string) {
    return this.request<ContentRunSummary>(`/workflow-runs/${runId}/materials/${materialId}`, { method: "POST" });
  }
  listHumanTasks(query: ListQuery = {}) { return this.request<Page<HumanTaskSummary>>(`/human-tasks?${toQueryString(query)}`); }
  humanTaskCounts() { return this.request<HumanTaskCounts>("/human-tasks/counts"); }
  runHumanTaskAction(id: string, command: ActionCommand, etag: string) {
    return this.request<HumanTaskSummary>(`/human-tasks/${id}/actions`, {
      method: "POST",
      body: JSON.stringify(command),
      headers: { "If-Match": etag },
    });
  }
  listMaterials(query: ListQuery = {}) { return this.request<Page<MaterialSummary>>(`/materials?${toQueryString(query)}`); }
  createMaterial(command: MaterialCreate) {
    return this.request<MaterialSummary>("/materials", { method: "POST", body: JSON.stringify(command) });
  }
  async uploadMaterial(file: File, title: string, trustLabel: string): Promise<MaterialSummary> {
    const body = new FormData();
    body.append("file", file);
    body.append("title", title);
    body.append("trustLabel", trustLabel);
    // No Content-Type header: the browser must set the multipart boundary itself.
    return this.request<MaterialSummary>("/materials/upload", { method: "POST", body });
  }
  downloadMaterial(id: string, fallbackName: string) { return this.download(`/materials/${id}/file`, fallbackName); }
  listOrganizationMembers() { return this.request<MemberSummary[]>("/organization/members"); }
  listMembers(query: ListQuery = {}) { return this.request<Page<MemberSummary>>(`/members?${toQueryString(query)}`); }
  getMember(id: string) { return this.request<MemberSummary>(`/members/${id}`); }
  createMember(command: CreateMemberCommand) { return this.request<CreateMemberResult>("/members", { method: "POST", body: JSON.stringify(command) }); }
  updateMember(id: string, data: { role_id?: string; status?: string }) { return this.request<MemberSummary>(`/members/${id}`, { method: "PUT", body: JSON.stringify(data) }); }
  resetMemberPassword(id: string) { return this.request<ResetMemberPasswordResult>(`/members/${id}/reset-password`, { method: "POST", body: JSON.stringify({}) }); }
  listRoles() { return this.request<RoleSummary[]>("/roles"); }
  getRole(id: string) { return this.request<RoleDetail>(`/roles/${id}`); }
  updateRole(id: string, data: { name?: string; description?: string; permissions?: PermissionItem[] }) { return this.request<RoleDetail>(`/roles/${id}`, { method: "PUT", body: JSON.stringify(data) }); }
  listWorkflowTemplates(query: ListQuery = {}) { return this.request<Page<WorkflowTemplateSummary>>(`/workflow-templates?${toQueryString(query)}`); }
  getWorkflowTemplate(id: string) { return this.request<WorkflowTemplateDetail>(`/workflow-templates/${id}`); }
  publishWorkflowTemplate(id: string) { return this.request<WorkflowTemplateDetail>(`/workflow-templates/${id}/publish`, { method: "POST" }); }
  listAuditLogs(query: ListQuery = {}) { return this.request<Page<AuditEventSummary>>(`/audit-logs?${toQueryString(query)}`); }
  getAuditLog(id: string) { return this.request<AuditEventDetail>(`/audit-logs/${id}`); }
  listModelProviders() { return this.request<ModelProviderSummary[]>("/model-providers"); }
  listModelCatalog() { return this.request<ModelCatalogItem[]>("/model-catalog"); }
  listModelCredentials(query: ListQuery = {}) { return this.request<Page<ModelCredentialSummary>>(`/model-credentials?${toQueryString(query)}`); }
  createModelCredential(command: CreateModelCredentialCommand) { return this.request<ModelCredentialSummary>("/model-credentials", { method: "POST", body: JSON.stringify(command) }); }
  testModelCredential(id: string) { return this.request<ModelCredentialSummary>(`/model-credentials/${id}/test`, { method: "POST" }); }
  revokeModelCredential(id: string) { return this.request<void>(`/model-credentials/${id}`, { method: "DELETE" }); }
  listModelRoutePolicies() { return this.request<ModelRoutePolicySummary[]>("/model-routing-policies"); }
  getModelRoutePolicy(taskType: string) { return this.request<ModelRoutePolicyDetail>(`/model-routing-policies/${taskType}`); }
  upsertModelRoutePolicy(taskType: string, data: ModelRoutePolicyCreateRequest) { return this.request<ModelRoutePolicyDetail>(`/model-routing-policies/${taskType}`, { method: "PUT", body: JSON.stringify(data) }); }
  listQuotaPolicies() { return this.request<QuotaPolicyDetail[]>("/quotas"); }
  getQuotaPolicy(id: string) { return this.request<QuotaPolicyDetail>(`/quotas/${id}`); }
  getQuotaOverview() { return this.request<QuotaOverview>("/quotas/overview"); }
  upsertQuotaPolicy(metric: string, data: { period_type: "DAILY" | "MONTHLY" | "ROLLING_30D"; soft_limit: number | null; hard_limit: number | null; overage_allowed: boolean; status: "ACTIVE" | "DISABLED"; }) { return this.request<QuotaPolicyDetail>(`/quotas/${metric}`, { method: "PUT", body: JSON.stringify(data) }); }
}

export const apiClient = new HttpApiClient();
