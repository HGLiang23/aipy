"""Audit log query routes (read-only; writes happen via the audit helper)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_current_session, get_session_factory, require_tenant
from .. import repositories
from ..schemas import AuditEventDetail, AuditEventSummary, Page, TenantSession

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=Page[AuditEventSummary])
def list_audit_logs_endpoint(
    page: int = 1,
    page_size: int = 20,
    action: str | None = None,
    resource_type: str | None = None,
    actor_id: UUID | None = None,
    result: str | None = None,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> Page[AuditEventSummary]:
    return repositories.list_audit_events(
        get_session_factory(), ids[0], page, page_size,
        action=action, resource_type=resource_type, actor_id=actor_id, result=result,
    )


@router.get("/{event_id}", response_model=AuditEventDetail)
def get_audit_log_endpoint(
    event_id: UUID,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> AuditEventDetail:
    event = repositories.get_audit_event(get_session_factory(), ids[0], event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return event
