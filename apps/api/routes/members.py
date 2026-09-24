"""Member (tenant membership) management routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..dependencies import get_current_session, get_session_factory, require_tenant
from .. import repositories
from ..schemas import (
    CreateMemberRequest,
    CreateMemberResponse,
    MemberSummary,
    Page,
    ResetMemberPasswordResponse,
    TenantSession,
    UpdateMemberRequest,
)

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=Page[MemberSummary])
def list_members_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> Page[MemberSummary]:
    return repositories.list_members(get_session_factory(), ids[0], page, page_size)


@router.post("", response_model=CreateMemberResponse, status_code=status.HTTP_201_CREATED)
def create_member_endpoint(
    data: CreateMemberRequest,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> CreateMemberResponse:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    try:
        member = repositories.create_member(factory, tenant_id, data)
    except repositories.MemberConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    repositories.record_audit(
        factory, tenant_id,
        action="member.create", resource_type="member", resource_id=member.id,
        actor_id=actor_id, actor_label=session.user.displayName,
        # Never audit the password itself.
        after_data={
            "email": data.email, "displayName": data.displayName,
            "roleLabel": member.roleLabel, "status": member.status,
            "accountCreated": member.accountCreated,
        },
    )
    return member


@router.get("/{member_id}", response_model=MemberSummary)
def get_member_endpoint(
    member_id: UUID,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> MemberSummary:
    member = repositories.get_member(get_session_factory(), ids[0], member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return member


@router.put("/{member_id}", response_model=MemberSummary)
def update_member_endpoint(
    member_id: UUID,
    data: UpdateMemberRequest,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> MemberSummary:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    before = repositories.get_member(factory, tenant_id, member_id)
    if before is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    member = repositories.update_member(factory, tenant_id, member_id, data)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    repositories.record_audit(
        factory, tenant_id,
        action="member.update", resource_type="member", resource_id=str(member_id),
        actor_id=actor_id, actor_label=session.user.displayName,
        before_data={"roleLabel": before.roleLabel, "status": before.status},
        after_data={"roleLabel": member.roleLabel, "status": member.status},
    )
    return member


@router.post("/{member_id}/reset-password", response_model=ResetMemberPasswordResponse)
def reset_member_password_endpoint(
    member_id: UUID,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> ResetMemberPasswordResponse:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    try:
        result = repositories.reset_member_password(factory, tenant_id, member_id)
    except repositories.MemberStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    repositories.record_audit(
        factory, tenant_id,
        action="member.password_reset", resource_type="member", resource_id=str(member_id),
        actor_id=actor_id, actor_label=session.user.displayName,
        # Never audit the password itself.
        after_data={"email": result.email, "displayName": result.displayName},
    )
    return result
