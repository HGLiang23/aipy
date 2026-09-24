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

// ── Member & Role types ──────────────────────────────────────────

export interface MemberSummary extends ResourceAuthorization { id: string; displayName: string; email: string; roleLabel: string; status: "INVITED" | "ACTIVE" | "SUSPENDED" | "LEFT"; jobTitle?: string | null; joinedAt?: string | null; }

export interface CreateMemberCommand { email: string; displayName: string; role_id: string; job_title?: string | null; }

// initialPassword is returned exactly once, by the create call only.
// It is null when an existing platform account was reused for this tenant.
export interface CreateMemberResult extends MemberSummary { initialPassword?: string | null; accountCreated: boolean; }

// Same write-once contract as creation: the new password is never persisted client-side.
export interface ResetMemberPasswordResult { memberId: string; displayName: string; email: string; password: string; }

export interface PermissionItem { code: string; dataScope?: string | null; }

export interface RoleSummary { id: string; code: string; name: string; description?: string | null; isBuiltin: boolean; isDefault: boolean; permissionCount: number; }

export interface RoleDetail extends RoleSummary { permissions: PermissionItem[]; memberCount: number; }

// ── Workflow template types ───────────────────────────────────────

export interface WorkflowNode {
  node_key: string;
  node_type: string;
  title: string;
  execution_mode: string;
  sequence_no: number;
  max_attempts: number;
  quality_threshold: number | null;
  timeout_seconds: number | null;
}

export interface WorkflowTemplateSummary extends ResourceAuthorization {
  id: string;
  code: string;
  name: string;
  category: "SYSTEM" | "TENANT";
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED";
  description: string | null;
  nodeCount: number;
  currentVersion: number | null;
}

export interface WorkflowTemplateDetail extends WorkflowTemplateSummary {
  nodes: WorkflowNode[];
  policy: Record<string, unknown> | null;
}

// ── Audit log types ───────────────────────────────────────────────

export interface AuditEventSummary {
  id: string;
  occurredAt: string;
  actorType: "USER" | "SYSTEM" | "PLATFORM" | string;
  actorLabel: string | null;
  action: string;
  resourceType: string;
  resourceId: string | null;
  result: "SUCCESS" | "FAILURE" | "DENIED" | string;
  reason: string | null;
}

export interface AuditEventDetail extends AuditEventSummary {
  actorId: string | null;
  resourceVersionId: string | null;
  requestId: string | null;
  traceId: string | null;
  ipHash: string | null;
  userAgent: string | null;
  beforeData: Record<string, unknown> | null;
  afterData: Record<string, unknown> | null;
}

// ── Model credential types ────────────────────────────────────────

export interface ModelProviderSummary {
  id: string;
  code: string;
  name: string;
  apiStyle: string;
  baseUrl: string | null;
}

export interface ModelCatalogItem {
  id: string;
  providerId: string;
  providerCode: string;
  modelCode: string;
  displayName: string;
  capabilityType: string;
  contextWindow: number;
  supportsStructuredOutput: boolean;
  inputPricePerMillion: number;
  outputPricePerMillion: number;
  currencyCode: string;
}

export interface ModelCredentialSummary extends ResourceAuthorization {
  id: string;
  providerId: string;
  providerName: string;
  name: string;
  ownershipType: "PLATFORM" | "BYOK";
  // Display-only masked preview; the raw secret is never returned.
  secretMasked: string;
  status: "ACTIVE" | "INVALID" | "REVOKED";
  lastVerifiedAt: string | null;
  lastVerifyMessage: string | null;
}

export interface CreateModelCredentialCommand {
  provider_id: string;
  name: string;
  ownership_type: "PLATFORM" | "BYOK";
  secret: string;
}

// ── Model routing policy types ────────────────────────────────────

export interface ModelRouteCandidate {
  priority: number;
  modelDefinitionId: string;
  modelCode: string;
  modelDisplayName: string;
  credentialId: string | null;
  temperature: number;
  maxOutputTokens: number;
  allowedForPublish: boolean;
}

export interface ModelRoutePolicySummary extends ResourceAuthorization {
  id: string;
  taskType: string;
  name: string;
  dailyCostLimit: number | null;
  perCallTimeoutSeconds: number;
  status: "ACTIVE" | "DISABLED";
  candidateCount: number;
}

export interface ModelRoutePolicyDetail extends ModelRoutePolicySummary {
  candidates: ModelRouteCandidate[];
}

// ── Quota & alert types ───────────────────────────────────────────

export type QuotaPeriodType = "DAILY" | "MONTHLY" | "ROLLING_30D";
export type QuotaLevel = "NORMAL" | "WARNING" | "EXCEEDED" | "NO_LIMIT";

export interface QuotaUsage {
  used: number;
  reserved: number;
  usageRatio: number | null;
  level: QuotaLevel;
  periodStart: string | null;
  periodEnd: string | null;
}

export interface QuotaPolicySummary extends ResourceAuthorization {
  id: string;
  metric: string;
  metricLabel: string;
  unit: string;
  periodType: QuotaPeriodType;
  softLimit: number | null;
  hardLimit: number | null;
  overageAllowed: boolean;
  status: "ACTIVE" | "DISABLED";
}

export interface QuotaPolicyDetail extends QuotaPolicySummary {
  usage: QuotaUsage;
}

export interface QuotaOverview {
  policyCount: number;
  activeCount: number;
  warningCount: number;
  exceededCount: number;
  generatedAt: string;
}
