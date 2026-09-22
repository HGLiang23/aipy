export type PermissionCode =
  | "batch:view" | "batch:create" | "batch:start" | "batch:pause" | "batch:resume" | "batch:cancel"
  | "content:view" | "content:create" | "content:edit" | "content:assign" | "content:delete"
  | "artifact:view" | "artifact:edit" | "artifact:regenerate" | "artifact:lock" | "artifact:compare" | "artifact:restore"
  | "source:view" | "source:create" | "source:edit" | "source:delete" | "source:collect"
  | "workflow:view" | "workflow:configure" | "workflow:execute" | "workflow:override"
  | "review:view" | "review:claim" | "review:approve" | "review:reject" | "review:reassign"
  | "publication:view" | "publication:preview" | "publication:export" | "publication:publish" | "publication:withdraw"
  | "model:view" | "model:configure" | "model:credential_manage"
  | "quota:view" | "quota:configure" | "member:view" | "member:manage"
  | "role:view" | "role:manage" | "audit:view" | "audit:export";

export type DataScope = "TENANT_ALL" | "TEAM" | "BRAND" | "ASSIGNED" | "CREATED_BY_ME" | "CUSTOM";
export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";
export interface TenantSummary { id: string; name: string; slug: string; timezone: string; status: "ACTIVE" | "FROZEN"; }
export interface WorkspaceSummary { id: string; name: string; }
export interface SessionUser { id: string; displayName: string; email: string; roleLabel: string; dataScopes: DataScope[]; }
export interface TenantSession { tenant: TenantSummary; workspace: WorkspaceSummary; user: SessionUser; permissions: PermissionCode[]; }
export interface ResourceAuthorization { allowed_actions: string[]; denial_reason?: string; etag: string; version: number; }
export interface ContentRunSummary extends ResourceAuthorization { id: string; title: string; brand: string; stageLabel: string; statusLabel: string; tone: StatusTone; owner: string; updatedAt: string; }
export interface HumanTaskSummary extends ResourceAuthorization { id: string; title: string; type: string; reason: string; priority: "高" | "普通"; brand: string; owner: string; dueLabel: string; }
export interface MaterialSummary extends ResourceAuthorization { id: string; title: string; summary: string; source: string; type: string; trustLabel: string; tone: StatusTone; updatedAt: string; }
