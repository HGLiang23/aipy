"""Role and permission management routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_current_session, get_session_factory, require_tenant
from .. import repositories
from ..schemas import RoleDetail, RoleSummary, TenantSession, UpdateRoleRequest

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleSummary])
def list_roles_endpoint(
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> list[RoleSummary]:
    return repositories.list_roles(get_session_factory(), ids[0])


@router.get("/{role_id}", response_model=RoleDetail)
def get_role_endpoint(
    role_id: UUID,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> RoleDetail:
    role = repositories.get_role(get_session_factory(), ids[0], role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.put("/{role_id}", response_model=RoleDetail)
def update_role_endpoint(
    role_id: UUID,
    data: UpdateRoleRequest,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> RoleDetail:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    before = repositories.get_role(factory, tenant_id, role_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Role not found")
    try:
        role = repositories.update_role(
            factory, tenant_id, role_id,
            name=data.name,
            description=data.description,
            permissions=data.permissions,
        )
    except IntegrityError as exc:
        # (tenant_id, name) is unique: another role already uses this name.
        raise HTTPException(status_code=409, detail="已存在同名角色，请换一个名称") from exc
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    repositories.record_audit(
        factory, tenant_id,
        action="role.update", resource_type="role", resource_id=str(role_id),
        actor_id=actor_id, actor_label=session.user.displayName,
        before_data={"name": before.name, "permissionCount": before.permissionCount},
        after_data={"name": role.name, "permissionCount": role.permissionCount},
    )
    return role
