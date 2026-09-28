import type {
  ContentRunCounts,
  ContentRunDetail,
  ContentRunSummary,
  ExportSummary,
  HumanTaskCounts,
  HumanTaskSummary,
  MaterialSummary,
  MemberSummary,
  TenantSession,
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
  listMembers(): Promise<MemberSummary[]>;
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
  listMembers() { return this.request<MemberSummary[]>("/organization/members"); }
}

export const apiClient = new HttpApiClient();
