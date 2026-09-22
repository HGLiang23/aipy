"""Trusted request identity context.

These models are constructed from verified credentials. Application code must
never merge tenant or actor identifiers from request payloads into them.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActorType(StrEnum):
    USER = "user"
    SERVICE = "service"


class ActorContext(BaseModel):
    """The authenticated actor and its organizational memberships."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: UUID
    actor_type: ActorType
    role_ids: tuple[UUID, ...] = ()
    team_ids: tuple[UUID, ...] = ()
    workspace_ids: tuple[UUID, ...] = ()
    session_id: UUID | None = None


class TenantContext(BaseModel):
    """Tenant boundary derived exclusively from a verified access token."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: UUID
    actor: ActorContext
    request_id: str = Field(min_length=1, max_length=128)

    @property
    def actor_id(self) -> UUID:
        return self.actor.actor_id

    @property
    def actor_type(self) -> ActorType:
        return self.actor.actor_type

    @property
    def role_ids(self) -> tuple[UUID, ...]:
        return self.actor.role_ids

    @property
    def team_ids(self) -> tuple[UUID, ...]:
        return self.actor.team_ids

    @property
    def workspace_ids(self) -> tuple[UUID, ...]:
        return self.actor.workspace_ids

    @property
    def session_id(self) -> UUID | None:
        return self.actor.session_id
