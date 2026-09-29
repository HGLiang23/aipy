"""Organization routes: tenant member directory used by the assign picker."""

from fastapi import APIRouter, Depends

from aipy.modules.authorization.domain.models import ResourceContext
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
from ..schemas import MemberSummary, TenantSession

router = APIRouter(prefix="/organization", tags=["organization"])


@router.get("/members", response_model=list[MemberSummary])
def list_members(
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> list[MemberSummary]:
    """Active tenant members, for assigning human tasks and the member directory."""

    decision = authorizer.authorize(
        subject, "member:view", ResourceContext(tenant_id=subject.tenant_id, resource_type="member")
    )
    if not decision.allowed:
        reason = decision.denial_reason.value if decision.denial_reason else "forbidden"
        raise ActionError(
            status_code=403, code=reason.lower(), detail="current role may not view members"
        ).as_http_exception()
    return repositories.list_members(get_session_factory(), subject)
