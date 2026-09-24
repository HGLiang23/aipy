"""Model provider catalog and tenant credential routes.

Security: the raw secret is write-only. Neither the list nor the create response
ever echoes it — only a masked preview is returned.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_current_session, get_session_factory, require_tenant
from .. import repositories
from ..schemas import (
    CreateModelCredentialRequest,
    ModelCatalogItem,
    ModelCredentialSummary,
    ModelProviderSummary,
    Page,
    TenantSession,
)

router = APIRouter(tags=["model-credentials"])


@router.get("/model-providers", response_model=list[ModelProviderSummary])
def list_model_providers_endpoint(
    _: TenantSession = Depends(get_current_session),
) -> list[ModelProviderSummary]:
    return repositories.list_model_providers(get_session_factory())


@router.get("/model-catalog", response_model=list[ModelCatalogItem])
def list_model_catalog_endpoint(
    _: TenantSession = Depends(get_current_session),
) -> list[ModelCatalogItem]:
    return repositories.list_model_catalog(get_session_factory())


@router.get("/model-credentials", response_model=Page[ModelCredentialSummary])
def list_model_credentials_endpoint(
    page: int = 1,
    page_size: int = 20,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> Page[ModelCredentialSummary]:
    return repositories.list_model_credentials(get_session_factory(), ids[0], page, page_size)


@router.get("/model-credentials/{credential_id}", response_model=ModelCredentialSummary)
def get_model_credential_endpoint(
    credential_id: UUID,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    _: TenantSession = Depends(get_current_session),
) -> ModelCredentialSummary:
    cred = repositories.get_model_credential(get_session_factory(), ids[0], credential_id)
    if cred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    return cred


@router.post("/model-credentials", response_model=ModelCredentialSummary, status_code=201)
def create_model_credential_endpoint(
    data: CreateModelCredentialRequest,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> ModelCredentialSummary:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    try:
        cred = repositories.create_model_credential(factory, tenant_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IntegrityError as exc:
        # (tenant_id, provider_id, name) is unique: a same-named credential already exists.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该供应商下已存在同名凭证，请换一个名称",
        ) from exc
    if cred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    repositories.record_audit(
        factory, tenant_id,
        action="model_credential.create", resource_type="model_credential",
        resource_id=cred.id, actor_id=actor_id, actor_label=session.user.displayName,
        # NOTE: only the masked preview is audited; the secret never enters the log.
        after_data={"name": cred.name, "providerName": cred.providerName, "secretMasked": cred.secretMasked},
    )
    return cred


@router.post("/model-credentials/{credential_id}/test", response_model=ModelCredentialSummary)
def test_model_credential_endpoint(
    credential_id: UUID,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> ModelCredentialSummary:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    cred = repositories.verify_model_credential(factory, tenant_id, credential_id)
    if cred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    repositories.record_audit(
        factory, tenant_id,
        action="model_credential.test", resource_type="model_credential",
        resource_id=credential_id, actor_id=actor_id, actor_label=session.user.displayName,
        after_data={"status": cred.status, "message": cred.lastVerifyMessage},
    )
    return cred


@router.delete("/model-credentials/{credential_id}", status_code=204)
def revoke_model_credential_endpoint(
    credential_id: UUID,
    ids: tuple[UUID, UUID] = Depends(require_tenant),
    session: TenantSession = Depends(get_current_session),
) -> None:
    factory = get_session_factory()
    tenant_id, actor_id = ids
    if not repositories.revoke_model_credential(factory, tenant_id, credential_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    repositories.record_audit(
        factory, tenant_id,
        action="model_credential.revoke", resource_type="model_credential",
        resource_id=credential_id, actor_id=actor_id, actor_label=session.user.displayName,
    )
