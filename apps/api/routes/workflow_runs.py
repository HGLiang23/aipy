"""Content run (workflow run) routes."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

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
from ..http_utils import attachment_header
from ..repositories import DEFAULT_EXPORT_MEDIA_TYPE, EXPORT_MEDIA_TYPES
from ..schemas import (
    ActionRequest,
    ContentRunCounts,
    ContentRunDetail,
    ContentRunSummary,
    CreateContentRunCommand,
    ExportSummary,
    Page,
    TenantSession,
)

# (re)start actions hand the run off to Celery; the synchronous flip to RUNNING
# already happened inside apply_content_action, so the board updates immediately.
_ASYNC_RUN_ACTIONS = frozenset({"rerun", "resume"})

router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])


@router.get("", response_model=Page[ContentRunSummary])
def list_workflow_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> Page[ContentRunSummary]:
    return repositories.list_content_runs(
        get_session_factory(), subject, authorizer, page, page_size, query=q, status=status_filter
    )


@router.post("", response_model=ContentRunSummary, status_code=status.HTTP_201_CREATED)
def create_workflow_run(
    command: CreateContentRunCommand,
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> ContentRunSummary:
    """Create a run and start it; the worker generates the body."""

    try:
        created = repositories.create_content_run(
            get_session_factory(), subject, authorizer, command, subject.actor.actor_id
        )
    except ActionError as exc:
        raise exc.as_http_exception() from exc

    from apps.worker.tasks import enqueue_content_run

    enqueue_content_run(created.id, subject.tenant_id, subject.actor.actor_id)
    return created


# Declared before ``/{run_id}`` so the literal path wins over the path parameter.
@router.get("/counts", response_model=ContentRunCounts)
def content_run_counts(
    subject: TenantContext = Depends(get_tenant_context),
    _: TenantSession = Depends(get_current_session),
) -> ContentRunCounts:
    """Status totals for the overview metrics."""

    return repositories.content_run_counts(get_session_factory(), subject)


@router.get("/{run_id}", response_model=ContentRunDetail)
def get_workflow_run(
    run_id: str,
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> ContentRunDetail:
    run = repositories.get_content_run_detail(get_session_factory(), subject, authorizer, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="content run not found")
    return run


@router.post("/{run_id}/actions", response_model=ContentRunSummary)
def run_content_action(
    run_id: str,
    command: ActionRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> ContentRunSummary:
    """Apply a state transition; ``If-Match`` must carry the version read."""

    try:
        result = repositories.apply_content_action(
            get_session_factory(),
            subject,
            authorizer,
            run_id,
            command.action,
            if_match,
            subject.actor.actor_id,
        )
    except ActionError as exc:
        raise exc.as_http_exception() from exc

    if command.action in _ASYNC_RUN_ACTIONS:
        from apps.worker.tasks import enqueue_content_run

        enqueue_content_run(run_id, subject.tenant_id, subject.actor.actor_id)
    return result


@router.get("/{run_id}/exports", response_model=list[ExportSummary])
def list_run_exports(
    run_id: str,
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> list[ExportSummary]:
    """Export history for a run, newest first."""

    try:
        return repositories.list_content_exports(get_session_factory(), subject, authorizer, run_id)
    except ActionError as exc:
        raise exc.as_http_exception() from exc


@router.get("/{run_id}/exports/{export_id}/download")
def download_run_export(
    run_id: str,
    export_id: str,
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> Response:
    """Stream one export artifact back as a file download."""

    try:
        artifact = repositories.get_content_export(
            get_session_factory(), subject, authorizer, run_id, export_id
        )
    except ActionError as exc:
        raise exc.as_http_exception() from exc

    suffix = ".md" if artifact.format == "markdown" else ""
    return Response(
        content=artifact.payload,
        media_type=EXPORT_MEDIA_TYPES.get(artifact.format, DEFAULT_EXPORT_MEDIA_TYPE),
        headers={"Content-Disposition": attachment_header(f"{artifact.title}{suffix}")},
    )


@router.post("/{run_id}/materials/{material_id}", response_model=ContentRunSummary)
def attach_material(
    run_id: str,
    material_id: str,
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> ContentRunSummary:
    """Link one material to a run; idempotent, used by the library's add button."""

    try:
        return repositories.link_material_to_run(
            get_session_factory(),
            subject,
            authorizer,
            run_id,
            material_id,
            subject.actor.actor_id,
        )
    except ActionError as exc:
        raise exc.as_http_exception() from exc
