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
