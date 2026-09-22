"""Framework-independent authorization policy models."""

import re
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aipy.shared.security.errors import AuthorizationDeniedError

_PERMISSION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$")


class Permission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not _PERMISSION_PATTERN.fullmatch(value):
            raise ValueError("permission must use the resource:action format")
        return value

    @property
    def resource(self) -> str:
        return self.code.split(":", maxsplit=1)[0]

    @property
    def action(self) -> str:
        return self.code.split(":", maxsplit=1)[1]


class DataScope(StrEnum):
    TENANT_ALL = "TENANT_ALL"
    WORKSPACE = "WORKSPACE"
    TEAM = "TEAM"
    ASSIGNED = "ASSIGNED"
    CREATED_BY_ME = "CREATED_BY_ME"
    CUSTOM = "CUSTOM"


class CustomScopeConstraint(BaseModel):
    """Conjunctive custom constraint; populated dimensions must all match."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_ids: frozenset[UUID] = frozenset()
    team_ids: frozenset[UUID] = frozenset()
    resource_ids: frozenset[UUID] = frozenset()

    @model_validator(mode="after")
    def require_at_least_one_dimension(self) -> "CustomScopeConstraint":
        if not (self.workspace_ids or self.team_ids or self.resource_ids):
            raise ValueError("custom scope requires at least one constrained dimension")
        return self


class DataScopeGrant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: DataScope
    workspace_ids: frozenset[UUID] = frozenset()
    team_ids: frozenset[UUID] = frozenset()
    custom: CustomScopeConstraint | None = None

    @model_validator(mode="after")
    def validate_scope_configuration(self) -> "DataScopeGrant":
        if self.scope is DataScope.CUSTOM and self.custom is None:
            raise ValueError("CUSTOM data scope requires custom constraints")
        if self.scope is not DataScope.CUSTOM and self.custom is not None:
            raise ValueError("custom constraints are only valid for CUSTOM data scope")
        return self


class PermissionGrant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    permission: Permission
    data_scopes: tuple[DataScopeGrant, ...] = ()


class WorkflowStatePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    permission: Permission
    allowed_states: frozenset[str] = Field(min_length=1)


class SeparationOfDutiesPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_permissions: frozenset[str] = frozenset({"review:approve"})
    publishing_permissions: frozenset[str] = frozenset({"publication:publish"})
    forbid_submitter_approval: bool = True
    forbid_creator_approval: bool = True
    forbid_editor_publish: bool = True
    forbid_approver_publish: bool = False

    @field_validator("approval_permissions", "publishing_permissions")
    @classmethod
    def validate_permission_codes(cls, values: frozenset[str]) -> frozenset[str]:
        for value in values:
            if not _PERMISSION_PATTERN.fullmatch(value):
                raise ValueError("duty permission must use the resource:action format")
        return values


class AuthorizationPolicy(BaseModel):
    """Resolved, actor-specific policy snapshot returned by a repository."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_active: bool = True
    actor_active: bool = True
    permission_grants: tuple[PermissionGrant, ...] = ()
    workflow_state_policies: tuple[WorkflowStatePolicy, ...] = ()
    separation_of_duties: SeparationOfDutiesPolicy = SeparationOfDutiesPolicy()


class ResourceContext(BaseModel):
    """Only authorization-relevant resource metadata, loaded server-side."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: UUID
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: UUID | None = None
    workspace_id: UUID | None = None
    team_id: UUID | None = None
    assigned_to: UUID | None = None
    created_by: UUID | None = None
    submitted_by: UUID | None = None
    last_edited_by: UUID | None = None
    approved_by_ids: frozenset[UUID] = frozenset()
    workflow_state: str | None = None


class DenialReason(StrEnum):
    INVALID_PERMISSION = "INVALID_PERMISSION"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    RESOURCE_TYPE_MISMATCH = "RESOURCE_TYPE_MISMATCH"
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    TENANT_INACTIVE = "TENANT_INACTIVE"
    ACTOR_INACTIVE = "ACTOR_INACTIVE"
    PERMISSION_MISSING = "PERMISSION_MISSING"
    DATA_SCOPE_MISMATCH = "DATA_SCOPE_MISMATCH"
    WORKFLOW_STATE_DENIED = "WORKFLOW_STATE_DENIED"
    SEPARATION_OF_DUTIES = "SEPARATION_OF_DUTIES"


class AuthorizationDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    permission: str
    denial_reason: DenialReason | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "AuthorizationDecision":
        if self.allowed and self.denial_reason is not None:
            raise ValueError("allowed decision cannot include denial_reason")
        if not self.allowed and self.denial_reason is None:
            raise ValueError("denied decision requires denial_reason")
        return self

    def require_allowed(self) -> None:
        if not self.allowed:
            raise AuthorizationDeniedError(
                reason=self.denial_reason.value if self.denial_reason is not None else None
            )
