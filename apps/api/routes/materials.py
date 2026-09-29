"""Material (source library) routes."""

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

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
from ..repositories import MAX_UPLOAD_BYTES
from ..schemas import CreateMaterialCommand, MaterialSummary, Page, TenantSession
from ..url_import import UrlImportError

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=Page[MaterialSummary])
def list_materials(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    type_filter: str | None = Query(default=None, alias="type", max_length=32),
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> Page[MaterialSummary]:
    # Call through the module: a bare ``list_materials`` would resolve to this
    # handler itself (same name) and recurse.
    return repositories.list_materials(
        get_session_factory(), subject, authorizer, page, page_size, query=q, type_=type_filter
    )


@router.post("", response_model=MaterialSummary, status_code=status.HTTP_201_CREATED)
def create_material(
    command: CreateMaterialCommand,
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> MaterialSummary:
    """Register a source. When ``url`` is given the page is fetched for its title."""

    try:
        return repositories.create_material(
            get_session_factory(), subject, authorizer, command, subject.actor.actor_id
        )
    except UrlImportError as exc:
        raise ActionError(400, "url_unreachable", str(exc)).as_http_exception() from exc
    except ActionError as exc:
        raise exc.as_http_exception() from exc


@router.post("/upload", response_model=MaterialSummary, status_code=status.HTTP_201_CREATED)
def upload_material(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    trust_label: str = Form(default="待复核", alias="trustLabel"),
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> MaterialSummary:
    """Store an uploaded file as a material's original artifact."""

    # Read one byte past the cap so an oversized upload is rejected rather than
    # silently truncated into a corrupt "original".
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    try:
        return repositories.create_uploaded_material(
            get_session_factory(),
            subject,
            authorizer,
            filename=file.filename or "未命名文件",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            title=title,
            trust_label=trust_label,
            actor_id=subject.actor.actor_id,
        )
    except ActionError as exc:
        raise exc.as_http_exception() from exc


@router.get("/{material_id}", response_model=MaterialSummary)
def get_material(
    material_id: str,
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> MaterialSummary:
    material = repositories.get_material(get_session_factory(), subject, authorizer, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="material not found")
    return material


@router.get("/{material_id}/file")
def download_material_file(
    material_id: str,
    subject: TenantContext = Depends(get_tenant_context),
    authorizer: AuthorizationService = Depends(get_authorization_service),
    _: TenantSession = Depends(get_current_session),
) -> Response:
    """Stream the original bytes of an uploaded material."""

    try:
        stored = repositories.get_material_file(
            get_session_factory(), subject, authorizer, material_id
        )
    except ActionError as exc:
        raise exc.as_http_exception() from exc
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="material has no uploaded file"
        )
    return Response(
        content=stored.data,
        media_type=stored.content_type,
        headers={"Content-Disposition": attachment_header(stored.filename)},
    )
