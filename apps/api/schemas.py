"""API request/response models for the /api/v1 surface.

Field names intentionally match the JSON contract consumed by the frontend
(`web/lib/types.ts`) so no client-side adapter is required. The mixed
snake/camel casing mirrors the existing TypeScript types exactly.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    status: str
    statusLabel: str
    tone: str
    owner: str
    updatedAt: str


class ContentRunDetail(ContentRunSummary):
    """A single run plus the generated body.

    The body is deliberately absent from :class:`ContentRunSummary`: the board
    renders up to a hundred rows per page and has no use for the full text.
    """

    content: str | None = None


class HumanTaskSummary(ResourceAuthorization):
    id: str
    title: str
    type: str
    reason: str
    priority: Literal["高", "普通"]
    brand: str
    owner: str
    dueLabel: str
    statusLabel: str


class MaterialSummary(ResourceAuthorization):
    id: str
    title: str
    summary: str
    source: str
    type: str
    trustLabel: str
    tone: str
    updatedAt: str


class MemberSummary(BaseModel):
    id: str
    displayName: str
    roleLabel: str


class ExportSummary(BaseModel):
    """One row of a content run's export history."""

    id: str
    title: str
    format: str
    createdAt: str
    sizeBytes: int


class ContentRunCounts(BaseModel):
    """Status totals for the overview page."""

    running: int
    waiting_human: int
    paused: int
    failed: int
    completed: int
    total: int


class HumanTaskCounts(BaseModel):
    """Per-tab totals for the human task board."""

    mine: int
    open: int
    team: int
    completed: int
    #: Tasks that are neither completed nor cancelled - what the sidebar badge shows.
    pending: int


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int


class LoginCommand(BaseModel):
    email: str
    password: str


class ActionRequest(BaseModel):
    action: str
    assigneeId: str | None = None


class CreateContentRunCommand(BaseModel):
    """Start a new content run. The run begins executing immediately."""

    title: str = Field(min_length=1, max_length=255)
    brand: str = Field(min_length=1, max_length=120)
    stageLabel: str = Field(default="素材准备", min_length=1, max_length=64)


class CreateMaterialCommand(BaseModel):
    """Register a source. A URL is fetched for its title and description."""

    title: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=2048)
    summary: str = Field(default="", max_length=4000)
    trustLabel: str = Field(default="待复核", min_length=1, max_length=32)

    @model_validator(mode="after")
    def require_title_or_url(self) -> "CreateMaterialCommand":
        has_title = bool(self.title and self.title.strip())
        has_url = bool(self.url and self.url.strip())
        if not (has_title or has_url):
            raise ValueError("either title or url is required")
        return self


class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    code: str = "error"
    detail: str | None = None
