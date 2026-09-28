"""Human task (human-in-the-loop) routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from aipy.modules.authorization.service import AuthorizationService
from aipy.shared.security.context import TenantContext

from .. import repositories
from ..dependencies import (
    get_authorization_service,
    get_current_session,
    get_session_factory,
    get_tenant_context,
)
from ..errors import ActionError
from ..schemas import ActionRequest, HumanTaskCounts, HumanTaskSummary, Page, TenantSession

router = APIRouter(prefix="/human-tasks", tags=["human-tasks"])


@router.get("", response_model=Page[HumanTaskSummary])
def list_human_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    mine: bool = Query(default=False, description="只返回当前用户被指派的任务"),
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> Page[HumanTaskSummary]:
    # Call through the module: a bare ``list_human_tasks`` would resolve to this
    # handler itself (same name) and recurse.
    return repositories.list_human_tasks(
        get_session_factory(),
        subject,
        authorizer,
        page,
        page_size,
        query=q,
        status=status_filter,
        assignee_id=subject.actor.actor_id if mine else None,
    )


# Declared before ``/{task_id}`` so the literal path wins over the path parameter.
@router.get("/counts", response_model=HumanTaskCounts)
def human_task_counts(
    subject: TenantContext = Depends(get_tenant_context),
    _: TenantSession = Depends(get_current_session),
) -> HumanTaskCounts:
    """Totals for the board's tabs, replacing the previously hard-coded badges."""

    return repositories.human_task_counts(get_session_factory(), subject, subject.actor.actor_id)


@router.get("/{task_id}", response_model=HumanTaskSummary)
def get_human_task(
    task_id: str,
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> HumanTaskSummary:
    task = repositories.get_human_task(get_session_factory(), subject, authorizer, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="human task not found")
    return task


@router.post("/{task_id}/actions", response_model=HumanTaskSummary)
def run_human_task_action(
    task_id: str,
    command: ActionRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> HumanTaskSummary:
    """Claim, reassign, submit, approve or reject a task under the state guard."""

    try:
        return repositories.apply_human_task_action(
            get_session_factory(),
            subject,
            authorizer,
            task_id,
            command.action,
            if_match,
            subject.actor.actor_id,
            assignee_id=_parse_assignee(command.assigneeId),
        )
    except ActionError as exc:
        raise exc.as_http_exception() from exc


def _parse_assignee(value: str | None) -> UUID | None:
    """``None`` means "leave it unassigned"; a malformed id is a client error."""

    if not value:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="assigneeId is not a valid uuid"
        ) from exc
