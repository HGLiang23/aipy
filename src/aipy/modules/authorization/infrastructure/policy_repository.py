"""Server-side policy resolution backed by the RBAC tables.

Permissions are read from ``membership_role -> role -> role_permission`` and
unioned across every active role the member holds. A membership that has no role
assigned yet falls back to the job-title catalogue, so tenants keep working
before (or without) an explicit role assignment.

Policies are always built from persisted state: a suspended tenant or a
non-active membership yields an inactive policy, which the authorization service
turns into a denial before any permission is consulted.
"""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from aipy.modules.authorization.domain.models import (
    AuthorizationPolicy,
    DataScope,
    DataScopeGrant,
    Permission,
    PermissionGrant,
)
from aipy.modules.authorization.domain.ports import AuthorizationPolicyRepository
from aipy.modules.authorization.infrastructure.role_catalog import (
    permissions_for_role,
    resolve_role,
)
from aipy.modules.organization.models import (
    AppUser,
    MembershipRole,
    Role,
    RolePermission,
    TenantMembership,
)
from aipy.modules.tenancy.models import Tenant
from aipy.shared.db import SessionFactory, tenant_session_scope
from aipy.shared.security.context import TenantContext

# Every role currently sees the whole tenant. Narrow scopes (WORKSPACE/TEAM)
# become usable once content entities carry workspace_id/team_id.
TENANT_WIDE_SCOPE = (DataScopeGrant(scope=DataScope.TENANT_ALL),)


class SqlAuthorizationPolicyRepository(AuthorizationPolicyRepository):
    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    def get_policy(self, subject: TenantContext) -> AuthorizationPolicy | None:
        with tenant_session_scope(self._factory, subject.tenant_id) as session:
            tenant = session.get(Tenant, subject.tenant_id)
            membership = self._active_membership(session, subject.tenant_id, subject.actor_id)
            user = session.get(AppUser, subject.actor_id)

            if tenant is None or membership is None or user is None:
                return None

            codes = _resolve_codes(
                self._permission_codes(session, subject.tenant_id, membership.id),
                membership.job_title,
            )

        return AuthorizationPolicy(
            tenant_active=tenant.status == "ACTIVE",
            actor_active=membership.status == "ACTIVE" and user.status == "ACTIVE",
            permission_grants=_grants(codes),
        )

    @staticmethod
    def _active_membership(
        session: Session, tenant_id: UUID, actor_id: UUID
    ) -> TenantMembership | None:
        return (
            session.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == actor_id,
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    def _permission_codes(
        session: Session, tenant_id: UUID, membership_id: UUID
    ) -> tuple[str, ...]:
        """Union of permission codes across every active role of the member."""

        return tuple(
            session.execute(
                select(RolePermission.permission_code)
                .join(Role, Role.id == RolePermission.role_id)
                .join(MembershipRole, MembershipRole.role_id == Role.id)
                .where(
                    MembershipRole.tenant_id == tenant_id,
                    MembershipRole.membership_id == membership_id,
                    Role.tenant_id == tenant_id,
                    Role.status == "ACTIVE",
                )
            )
            .scalars()
            .all()
        )


def _resolve_codes(codes: tuple[str, ...], job_title: str | None) -> tuple[str, ...]:
    """Prefer RBAC rows; fall back to the job-title catalogue when unassigned."""

    if codes:
        return codes
    return permissions_for_role(resolve_role(job_title))


def _grants(codes: tuple[str, ...]) -> tuple[PermissionGrant, ...]:
    """Build grants, dropping duplicates and malformed permission codes."""

    grants: list[PermissionGrant] = []
    for code in dict.fromkeys(codes):
        try:
            permission = Permission(code=code)
        except ValidationError:
            continue
        grants.append(PermissionGrant(permission=permission, data_scopes=TENANT_WIDE_SCOPE))
    return tuple(grants)
