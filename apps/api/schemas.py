"""API request/response models for the /api/v1 surface.

Field names intentionally match the JSON contract consumed by the frontend
(`web/lib/types.ts`) so no client-side adapter is required. The mixed
snake/camel casing mirrors the existing TypeScript types exactly.
"""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class TenantSummary(BaseModel):
    id: str
    name: str
    slug: str
    timezone: str
    status: Literal["ACTIVE", "FROZEN"]


class WorkspaceSummary(BaseModel):
    id: str
    name: str


class SessionUser(BaseModel):
    id: str
    displayName: str
    email: str
    roleLabel: str
    dataScopes: list[str]


class TenantSession(BaseModel):
    tenant: TenantSummary
    workspace: WorkspaceSummary
    user: SessionUser
    permissions: list[str]


class ResourceAuthorization(BaseModel):
    allowed_actions: list[str]
    etag: str
    version: int
    denial_reason: str | None = None


class ContentRunSummary(ResourceAuthorization):
    id: str
    title: str
    brand: str
    stageLabel: str
    statusLabel: str
    tone: str
    owner: str
    updatedAt: str


class HumanTaskSummary(ResourceAuthorization):
    id: str
    title: str
    type: str
    reason: str
    priority: Literal["高", "普通"]
    brand: str
    owner: str
    dueLabel: str


class MaterialSummary(ResourceAuthorization):
    id: str
    title: str
    summary: str
    source: str
    type: str
    trustLabel: str
    tone: str
    updatedAt: str


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


class LoginCommand(BaseModel):
    email: str
    password: str


class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    code: str = "error"
    detail: str | None = None


# ── Member schemas ────────────────────────────────────────────────

class MemberSummary(ResourceAuthorization):
    id: str
    displayName: str
    email: str
    roleLabel: str
    status: Literal["INVITED", "ACTIVE", "SUSPENDED", "LEFT"]
    jobTitle: str | None = None
    joinedAt: str | None = None


class UpdateMemberRequest(BaseModel):
    role_id: str | None = None
    status: Literal["ACTIVE", "SUSPENDED"] | None = None


class CreateMemberRequest(BaseModel):
    email: str
    displayName: str
    # Required on purpose: leaving it optional would fall back to the tenant's
    # is_default role (currently 租户管理员) and silently grant admin rights.
    role_id: str
    job_title: str | None = None


class CreateMemberResponse(MemberSummary):
    # Write-once: the generated password is only ever returned by the create call.
    # ``None`` means an existing platform account was reused (nothing to hand out).
    initialPassword: str | None = None
    accountCreated: bool = False


class ResetMemberPasswordResponse(BaseModel):
    memberId: str
    displayName: str
    email: str
    # Write-once, same contract as creation: surfaced in this response only.
    password: str


# ── Role schemas ──────────────────────────────────────────────────

class PermissionItem(BaseModel):
    code: str
    dataScope: str | None = None


class RoleSummary(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    isBuiltin: bool
    isDefault: bool
    permissionCount: int = 0


class RoleDetail(RoleSummary):
    permissions: list[PermissionItem] = []
    memberCount: int = 0


class UpdateRoleRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[PermissionItem] | None = None


# ── Workflow template DTOs ────────────────────────────────────────

class WorkflowNode(BaseModel):
    node_key: str
    node_type: str
    title: str
    execution_mode: str
    sequence_no: int
    max_attempts: int = 1
    quality_threshold: int | None = None
    timeout_seconds: int | None = None


class WorkflowTemplateSummary(ResourceAuthorization):
    id: str
    code: str
    name: str
    category: str
    status: str
    description: str | None = None
    nodeCount: int = 0
    currentVersion: int | None = None


class WorkflowTemplateDetail(WorkflowTemplateSummary):
    nodes: list[WorkflowNode] = []
    policy: dict | None = None


# ── Audit log DTOs ────────────────────────────────────────────────

class AuditEventSummary(BaseModel):
    id: str
    occurredAt: str
    actorType: str
    actorLabel: str | None = None
    action: str
    resourceType: str
    resourceId: str | None = None
    result: str
    reason: str | None = None


class AuditEventDetail(AuditEventSummary):
    actorId: str | None = None
    resourceVersionId: str | None = None
    requestId: str | None = None
    traceId: str | None = None
    ipHash: str | None = None
    userAgent: str | None = None
    beforeData: dict | None = None
    afterData: dict | None = None


# ── Model credential DTOs ─────────────────────────────────────────

class ModelProviderSummary(BaseModel):
    id: str
    code: str
    name: str
    apiStyle: str
    baseUrl: str | None = None


class ModelCatalogItem(BaseModel):
    id: str
    providerId: str
    providerCode: str
    modelCode: str
    displayName: str
    capabilityType: str
    contextWindow: int
    supportsStructuredOutput: bool
    inputPricePerMillion: float
    outputPricePerMillion: float
    currencyCode: str


class ModelCredentialSummary(ResourceAuthorization):
    id: str
    providerId: str
    providerName: str
    name: str
    ownershipType: str
    secretMasked: str
    status: str
    lastVerifiedAt: str | None = None
    lastVerifyMessage: str | None = None


class CreateModelCredentialRequest(BaseModel):
    provider_id: str
    name: str
    ownership_type: Literal["PLATFORM", "BYOK"] = "BYOK"
    # Write-only: never echoed back.
    secret: str | None = None


# ── Model routing policy DTOs ─────────────────────────────────────

class ModelRouteCandidateDTO(BaseModel):
    priority: int
    modelDefinitionId: str
    modelCode: str
    modelDisplayName: str
    credentialId: str | None = None
    temperature: float = 0.7
    maxOutputTokens: int = 2048
    allowedForPublish: bool = False


class ModelRoutePolicySummary(ResourceAuthorization):
    id: str
    taskType: str
    name: str
    dailyCostLimit: float | None = None
    perCallTimeoutSeconds: int = 60
    status: str
    candidateCount: int = 0


class ModelRoutePolicyDetail(ModelRoutePolicySummary):
    candidates: list[ModelRouteCandidateDTO] = []


class ModelRouteCandidateInput(BaseModel):
    model_definition_id: str
    credential_id: str | None = None
    temperature: float = 0.7
    max_output_tokens: int = 2048
    allowed_for_publish: bool = False


class UpsertModelRoutePolicyRequest(BaseModel):
    name: str
    daily_cost_limit: float | None = None
    per_call_timeout_seconds: int = 60
    status: Literal["ACTIVE", "DISABLED"] = "ACTIVE"
    candidates: list[ModelRouteCandidateInput] = []


# ── Quota & alert DTOs ────────────────────────────────────────────

class QuotaPolicySummary(ResourceAuthorization):
    id: str
    metric: str
    metricLabel: str
    unit: str
    periodType: Literal["DAILY", "MONTHLY", "ROLLING_30D"]
    softLimit: float | None = None
    hardLimit: float | None = None
    overageAllowed: bool
    status: Literal["ACTIVE", "DISABLED"]


class QuotaUsageDTO(BaseModel):
    """Current-period usage against a policy, plus the derived alert level."""

    used: float
    reserved: float = 0.0
    usageRatio: float | None = None
    # NORMAL / WARNING (crossed soft) / EXCEEDED (crossed hard) / NO_LIMIT
    level: Literal["NORMAL", "WARNING", "EXCEEDED", "NO_LIMIT"]
    periodStart: str | None = None
    periodEnd: str | None = None


class QuotaPolicyDetail(QuotaPolicySummary):
    usage: QuotaUsageDTO


class QuotaOverviewBucket(BaseModel):
    """A usage bucket row for the overview timeline."""

    metric: str
    used: float
    reserved: float
    periodStart: str
    periodEnd: str


class QuotaOverview(BaseModel):
    """Aggregate card data for the quota dashboard."""

    policyCount: int
    activeCount: int
    warningCount: int
    exceededCount: int
    generatedAt: str


class UpsertQuotaPolicyRequest(BaseModel):
    period_type: Literal["DAILY", "MONTHLY", "ROLLING_30D"] = "MONTHLY"
    soft_limit: float | None = None
    hard_limit: float | None = None
    overage_allowed: bool = False
    status: Literal["ACTIVE", "DISABLED"] = "ACTIVE"
