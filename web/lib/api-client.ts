import type { ContentRunSummary, HumanTaskSummary, MaterialSummary, TenantSession } from "@/lib/types";

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
}

export class HttpApiClient implements ApiClient {
  constructor(private readonly baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1") {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const headers = new Headers(init?.headers);
    if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
    if (!response.ok) throw new ApiProblem(await response.json() as ProblemDetails);
    return response.json() as Promise<T>;
  }

  login(command: LoginCommand) { return this.request<TenantSession>("/auth/login", { method: "POST", body: JSON.stringify(command) }); }
  getSession() { return this.request<TenantSession>("/me"); }
  listContentRuns(query = new URLSearchParams()) { return this.request<Page<ContentRunSummary>>(`/workflow-runs?${query}`); }
  getContentRun(id: string) { return this.request<ContentRunSummary>(`/workflow-runs/${id}`); }
  listHumanTasks(query = new URLSearchParams()) { return this.request<Page<HumanTaskSummary>>(`/human-tasks?${query}`); }
  listMaterials(query = new URLSearchParams()) { return this.request<Page<MaterialSummary>>(`/materials?${query}`); }
}

export const apiClient = new HttpApiClient();
