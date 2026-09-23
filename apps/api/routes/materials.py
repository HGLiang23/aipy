"""Material (source library) routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import repositories
from ..dependencies import get_current_session, get_session_factory, require_tenant
from ..schemas import MaterialSummary, Page, TenantSession

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=Page[MaterialSummary])
def list_materials(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> Page[MaterialSummary]:
    # Call through the module: a bare ``list_materials`` would resolve to this
    # handler itself (same name) and recurse.
    return repositories.list_materials(get_session_factory(), ids[0], page, page_size)


@router.get("/{material_id}", response_model=MaterialSummary)
def get_material(
    material_id: str,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> MaterialSummary:
    material = repositories.get_material(get_session_factory(), ids[0], material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="material not found")
    return material
