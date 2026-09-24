"""Model routing policy routes (per task type: primary + fallback models)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_current_session, get_session_factory, require_tenant
from .. import repositories
from ..schemas import (
    ModelRoutePolicyDetail,
    ModelRoutePolicySummary,
    TenantSession,
    UpsertModelRoutePolicyRequest,
)

router = APIRouter(prefix="/model-routing-policies", tags=["model-routing"])


@router.get("", response_model=list[ModelRoutePolicySummary])
def list_model_route_policies_endpoint(
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> list[ModelRoutePolicySummary]:
    return repositories.list_model_route_policies(get_session_factory(), ids[0])


@router.get("/{task_type}", response_model=ModelRoutePolicyDetail)
def get_model_route_policy_endpoint(
    task_type: str,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> ModelRoutePolicyDetail:
    policy = repositories.get_model_route_policy(get_session_factory(), ids[0], task_type)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing policy not found")
    return policy


@router.put("/{task_type}", response_model=ModelRoutePolicyDetail)
def upsert_model_route_policy_endpoint(
    task_type: str,
    data: UpsertModelRoutePolicyRequest,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> ModelRoutePolicyDetail:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    before = repositories.get_model_route_policy(factory, tenant_id, task_type)
    try:
        policy = repositories.upsert_model_route_policy(factory, tenant_id, task_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing policy not found")
    repositories.record_audit(
        factory, tenant_id,
        action="model_routing.update", resource_type="model_route_policy",
        resource_id=policy.id, actor_id=actor_id, actor_label=session.user.displayName,
        before_data={"candidateCount": before.candidateCount if before else 0},
        after_data={"taskType": task_type, "candidateCount": policy.candidateCount},
    )
    return policy
