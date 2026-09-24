import type { AuditEventDetail, AuditEventSummary, ContentRunSummary, CreateMemberCommand, CreateMemberResult, CreateModelCredentialCommand, HumanTaskSummary, MaterialSummary, MemberSummary, ModelCatalogItem, ModelCredentialSummary, ModelProviderSummary, ModelRoutePolicyDetail, ModelRoutePolicySummary, PermissionItem, QuotaOverview, QuotaPolicyDetail, QuotaPolicySummary, ResetMemberPasswordResult, RoleDetail, RoleSummary, TenantSession, WorkflowTemplateDetail, WorkflowTemplateSummary } from "@/lib/types";

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

export interface ApiClient {
  login(command: LoginCommand): Promise<TenantSession>;
  getSession(): Promise<TenantSession>;
  listContentRuns(query?: URLSearchParams): Promise<Page<ContentRunSummary>>;
  getContentRun(id: string): Promise<ContentRunSummary>;
  listHumanTasks(query?: URLSearchParams): Promise<Page<HumanTaskSummary>>;
  listMaterials(query?: URLSearchParams): Promise<Page<MaterialSummary>>;
  listMembers(query?: URLSearchParams): Promise<Page<MemberSummary>>;
  getMember(id: string): Promise<MemberSummary>;
  createMember(command: CreateMemberCommand): Promise<CreateMemberResult>;
  updateMember(id: string, data: { role_id?: string; status?: string }): Promise<MemberSummary>;
  resetMemberPassword(id: string): Promise<ResetMemberPasswordResult>;
  listRoles(): Promise<RoleSummary[]>;
  getRole(id: string): Promise<RoleDetail>;
  updateRole(id: string, data: { name?: string; description?: string; permissions?: PermissionItem[] }): Promise<RoleDetail>;
  listWorkflowTemplates(query?: URLSearchParams): Promise<Page<WorkflowTemplateSummary>>;
  getWorkflowTemplate(id: string): Promise<WorkflowTemplateDetail>;
  publishWorkflowTemplate(id: string): Promise<WorkflowTemplateDetail>;
  listAuditLogs(query?: URLSearchParams): Promise<Page<AuditEventSummary>>;
  getAuditLog(id: string): Promise<AuditEventDetail>;
  listModelProviders(): Promise<ModelProviderSummary[]>;
  listModelCatalog(): Promise<ModelCatalogItem[]>;
  listModelCredentials(query?: URLSearchParams): Promise<Page<ModelCredentialSummary>>;
  createModelCredential(command: CreateModelCredentialCommand): Promise<ModelCredentialSummary>;
  testModelCredential(id: string): Promise<ModelCredentialSummary>;
  revokeModelCredential(id: string): Promise<void>;
  listModelRoutePolicies(): Promise<ModelRoutePolicySummary[]>;
  getModelRoutePolicy(taskType: string): Promise<ModelRoutePolicyDetail>;
  upsertModelRoutePolicy(taskType: string, data: {
    name: string;
    daily_cost_limit: number | null;
    per_call_timeout_seconds: number;
    status: "ACTIVE" | "DISABLED";
    candidates: Array<{ model_definition_id: string; temperature: number; max_output_tokens: number; allowed_for_publish: boolean }>;
  }): Promise<ModelRoutePolicyDetail>;
  listQuotaPolicies(): Promise<QuotaPolicyDetail[]>;
  getQuotaOverview(): Promise<QuotaOverview>;
  upsertQuotaPolicy(metric: string, data: {
    period_type: "DAILY" | "MONTHLY" | "ROLLING_30D";
    soft_limit: number | null;
    hard_limit: number | null;
    overage_allowed: boolean;
    status: "ACTIVE" | "DISABLED";
  }): Promise<QuotaPolicyDetail>;
}

export class HttpApiClient implements ApiClient {
  constructor(private readonly baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1") {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const headers = new Headers(init?.headers);
    if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
    if (!response.ok) throw new ApiProblem(await response.json() as ProblemDetails);
    // 204 No Content (e.g. DELETE) has no body to parse.
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  login(command: LoginCommand) { return this.request<TenantSession>("/auth/login", { method: "POST", body: JSON.stringify(command) }); }
  getSession() { return this.request<TenantSession>("/me"); }
  listContentRuns(query = new URLSearchParams()) { return this.request<Page<ContentRunSummary>>(`/workflow-runs?${query}`); }
  getContentRun(id: string) { return this.request<ContentRunSummary>(`/workflow-runs/${id}`); }
  listHumanTasks(query = new URLSearchParams()) { return this.request<Page<HumanTaskSummary>>(`/human-tasks?${query}`); }
  listMaterials(query = new URLSearchParams()) { return this.request<Page<MaterialSummary>>(`/materials?${query}`); }
  listMembers(query = new URLSearchParams()) { return this.request<Page<MemberSummary>>(`/members?${query}`); }
  getMember(id: string) { return this.request<MemberSummary>(`/members/${id}`); }
  createMember(command: CreateMemberCommand) { return this.request<CreateMemberResult>("/members", { method: "POST", body: JSON.stringify(command) }); }
  updateMember(id: string, data: { role_id?: string; status?: string }) { return this.request<MemberSummary>(`/members/${id}`, { method: "PUT", body: JSON.stringify(data) }); }
  resetMemberPassword(id: string) { return this.request<ResetMemberPasswordResult>(`/members/${id}/reset-password`, { method: "POST", body: JSON.stringify({}) }); }
  listRoles() { return this.request<RoleSummary[]>("/roles"); }
  getRole(id: string) { return this.request<RoleDetail>(`/roles/${id}`); }
  updateRole(id: string, data: { name?: string; description?: string; permissions?: PermissionItem[] }) { return this.request<RoleDetail>(`/roles/${id}`, { method: "PUT", body: JSON.stringify(data) }); }
  listWorkflowTemplates(query = new URLSearchParams()) { return this.request<Page<WorkflowTemplateSummary>>(`/workflow-templates?${query}`); }
  getWorkflowTemplate(id: string) { return this.request<WorkflowTemplateDetail>(`/workflow-templates/${id}`); }
  publishWorkflowTemplate(id: string) { return this.request<WorkflowTemplateDetail>(`/workflow-templates/${id}/publish`, { method: "POST" }); }
  listAuditLogs(query = new URLSearchParams()) { return this.request<Page<AuditEventSummary>>(`/audit-logs?${query}`); }
  getAuditLog(id: string) { return this.request<AuditEventDetail>(`/audit-logs/${id}`); }
  listModelProviders() { return this.request<ModelProviderSummary[]>("/model-providers"); }
  listModelCatalog() { return this.request<ModelCatalogItem[]>("/model-catalog"); }
  listModelCredentials(query = new URLSearchParams()) { return this.request<Page<ModelCredentialSummary>>(`/model-credentials?${query}`); }
  createModelCredential(command: CreateModelCredentialCommand) { return this.request<ModelCredentialSummary>("/model-credentials", { method: "POST", body: JSON.stringify(command) }); }
  testModelCredential(id: string) { return this.request<ModelCredentialSummary>(`/model-credentials/${id}/test`, { method: "POST" }); }
  revokeModelCredential(id: string) { return this.request<void>(`/model-credentials/${id}`, { method: "DELETE" }); }
  listModelRoutePolicies() { return this.request<ModelRoutePolicySummary[]>("/model-routing-policies"); }
  getModelRoutePolicy(taskType: string) { return this.request<ModelRoutePolicyDetail>(`/model-routing-policies/${taskType}`); }
  upsertModelRoutePolicy(taskType: string, data: Parameters<ApiClient["upsertModelRoutePolicy"]>[1]) { return this.request<ModelRoutePolicyDetail>(`/model-routing-policies/${taskType}`, { method: "PUT", body: JSON.stringify(data) }); }
  listQuotaPolicies() { return this.request<QuotaPolicyDetail[]>("/quotas"); }
  getQuotaOverview() { return this.request<QuotaOverview>("/quotas/overview"); }
  upsertQuotaPolicy(metric: string, data: Parameters<ApiClient["upsertQuotaPolicy"]>[1]) { return this.request<QuotaPolicyDetail>(`/quotas/${metric}`, { method: "PUT", body: JSON.stringify(data) }); }
}

export const apiClient = new HttpApiClient();
