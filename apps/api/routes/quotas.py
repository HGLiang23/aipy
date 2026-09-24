"""Quota policy routes: per-metric soft/hard limits and current usage."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_current_session, get_session_factory, require_tenant
from .. import repositories
from ..schemas import (
    QuotaOverview,
    QuotaPolicyDetail,
    TenantSession,
    UpsertQuotaPolicyRequest,
)

router = APIRouter(prefix="/quotas", tags=["quotas"])


@router.get("", response_model=list[QuotaPolicyDetail])
def list_quota_policies_endpoint(
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> list[QuotaPolicyDetail]:
    return repositories.list_quota_policies(get_session_factory(), ids[0])


@router.get("/overview", response_model=QuotaOverview)
def quota_overview_endpoint(
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> QuotaOverview:
    return repositories.quota_overview(get_session_factory(), ids[0])


@router.get("/{metric}", response_model=QuotaPolicyDetail)
def get_quota_policy_endpoint(
    metric: str,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> QuotaPolicyDetail:
    policy = repositories.get_quota_policy(get_session_factory(), ids[0], metric)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quota policy not found")
    return policy


@router.put("/{metric}", response_model=QuotaPolicyDetail)
def upsert_quota_policy_endpoint(
    metric: str,
    data: UpsertQuotaPolicyRequest,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> QuotaPolicyDetail:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    before = repositories.get_quota_policy(factory, tenant_id, metric)
    try:
        policy = repositories.upsert_quota_policy(factory, tenant_id, metric, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quota policy not found")
    repositories.record_audit(
        factory, tenant_id,
        action="quota.update", resource_type="quota_policy",
        resource_id=policy.id, actor_id=actor_id, actor_label=session.user.displayName,
        before_data={
            "softLimit": before.softLimit if before else None,
            "hardLimit": before.hardLimit if before else None,
        },
        after_data={"metric": metric, "softLimit": policy.softLimit, "hardLimit": policy.hardLimit},
    )
    return policy
