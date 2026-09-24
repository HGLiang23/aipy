"""Workflow template management routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_current_session, get_session_factory, require_tenant
from .. import repositories
from ..schemas import TenantSession, WorkflowTemplateDetail, WorkflowTemplateSummary, Page

router = APIRouter(prefix="/workflow-templates", tags=["workflow-templates"])


@router.get("", response_model=Page[WorkflowTemplateSummary])
def list_workflow_templates_endpoint(
    page: int = 1,
    page_size: int = 20,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> Page[WorkflowTemplateSummary]:
    return repositories.list_workflow_templates(get_session_factory(), ids[0], page, page_size)


@router.get("/{template_id}", response_model=WorkflowTemplateDetail)
def get_workflow_template_endpoint(
    template_id: UUID,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> WorkflowTemplateDetail:
    tpl = repositories.get_workflow_template(get_session_factory(), ids[0], template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Workflow template not found")
    return tpl


@router.post("/{template_id}/publish", response_model=WorkflowTemplateDetail)
def publish_workflow_template_endpoint(
    template_id: UUID,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> WorkflowTemplateDetail:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    tpl = repositories.publish_workflow_template(factory, tenant_id, template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Workflow template not found")
    repositories.record_audit(
        factory, tenant_id,
        action="workflow.publish", resource_type="workflow_template",
        resource_id=str(template_id),
        actor_id=actor_id, actor_label=session.user.displayName,
        after_data={"status": tpl.status, "currentVersion": tpl.currentVersion},
    )
    return tpl
