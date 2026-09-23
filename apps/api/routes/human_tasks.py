"""Human task (human-in-the-loop) routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import repositories
from ..dependencies import get_current_session, get_session_factory, require_tenant
from ..schemas import HumanTaskSummary, Page, TenantSession

router = APIRouter(prefix="/human-tasks", tags=["human-tasks"])


@router.get("", response_model=Page[HumanTaskSummary])
def list_human_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> Page[HumanTaskSummary]:
    # Call through the module: a bare ``list_human_tasks`` would resolve to this
    # handler itself (same name) and recurse.
    return repositories.list_human_tasks(get_session_factory(), ids[0], page, page_size)


@router.get("/{task_id}", response_model=HumanTaskSummary)
def get_human_task(
    task_id: str,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> HumanTaskSummary:
    task = repositories.get_human_task(get_session_factory(), ids[0], task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="human task not found")
    return task
