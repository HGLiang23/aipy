"""Content run (workflow run) routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import repositories
from ..dependencies import get_current_session, get_session_factory, require_tenant
from ..schemas import ContentRunSummary, Page, TenantSession

router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])


@router.get("", response_model=Page[ContentRunSummary])
def list_workflow_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> Page[ContentRunSummary]:
    return repositories.list_content_runs(get_session_factory(), ids[0], page, page_size)


@router.get("/{run_id}", response_model=ContentRunSummary)
def get_workflow_run(
    run_id: str,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> ContentRunSummary:
    run = repositories.get_content_run(get_session_factory(), ids[0], run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="content run not found")
    return run
