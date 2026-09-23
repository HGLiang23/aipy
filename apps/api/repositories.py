"""PostgreSQL-backed repositories for the /api/v1 surface.

These replace the in-memory seed with real SQLAlchemy queries. Every tenant-scoped
read/write goes through ``tenant_session_scope`` so Row-Level Security isolates
data by ``app.tenant_id``. The contract (returned schema models) is unchanged,
so routers and the frontend are unaffected.
"""

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aipy.modules.content.models import ContentRun, HumanTask, Material
from aipy.modules.identity.domain.models import TokenSubject
from aipy.modules.identity.infrastructure.passwords import PwdlibPasswordHasher
from aipy.modules.organization.models import AppUser, TenantMembership
from aipy.modules.tenancy.models import Tenant
from aipy.modules.brand.models import Workspace
from aipy.shared.db import SessionFactory, session_scope, set_user_context, tenant_session_scope
from aipy.shared.security.context import ActorType

from .schemas import (
    ContentRunSummary,
    HumanTaskSummary,
    MaterialSummary,
    Page,
    SessionUser,
    TenantSession,
    TenantSummary,
    WorkspaceSummary,
)

# The demo tenant uses a single administrator membership. There is no persisted
# role/permission table in the current schema, so the resolved policy is a static
# administrator grant. Replace with a real authorization repository when one exists.
ADMIN_ROLE_LABEL = "租户管理员"
ADMIN_DATA_SCOPES = ["TENANT_ALL"]
ADMIN_PERMISSIONS = [
    "batch:view", "batch:create", "content:view", "content:create", "content:edit",
    "content:assign", "artifact:view", "artifact:edit", "artifact:compare",
    "source:view", "source:create", "source:edit", "source:collect",
    "workflow:view", "workflow:configure", "workflow:execute", "review:view",
    "review:claim", "review:approve", "review:reject", "review:reassign",
    "publication:view", "publication:preview", "publication:export",
    "model:view", "model:configure", "model:credential_manage", "quota:view",
    "quota:configure", "member:view", "member:manage", "role:view",
    "role:manage", "audit:view",
]


def _etag(code: str, version: int) -> str:
    return f'"{code}-v{version}"'


def authenticate(factory: SessionFactory, email: str, password: str) -> TokenSubject | None:
    """Verify credentials against ``app_user`` and resolve the active tenant.

    ``tenant_membership`` is protected by FORCE ROW LEVEL SECURITY, so the
    membership lookup cannot use the tenant-isolation policy - there is no
    ``app.tenant_id`` yet at login time. Once the password is verified the session
    sets ``app.user_id``, which the permissive self-lookup policy added in migration
    ``20260724_0003`` uses to expose only that user's own membership rows.
    """

    with session_scope(factory) as session:
        user = session.execute(
            select(AppUser).where(AppUser.email == email)
        ).scalars().first()
        if user is None:
            return None
        if not PwdlibPasswordHasher().verify(password, user.password_hash):
            return None
        set_user_context(session, user.id)
        membership = session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user.id,
                TenantMembership.status == "ACTIVE",
            )
        ).scalars().first()
        if membership is None:
            return None
        return TokenSubject(
            tenant_id=membership.tenant_id,
            actor_id=user.id,
            actor_type=ActorType.USER,
            session_id=uuid4(),
        )


def build_session(
    factory: SessionFactory, tenant_id: UUID, actor_id: UUID
) -> TenantSession:
    """Assemble the dashboard session payload from persisted entities."""

    with tenant_session_scope(factory, tenant_id) as session:
        tenant = session.get(Tenant, tenant_id)
        workspace = session.execute(
            select(Workspace)
            .where(Workspace.tenant_id == tenant_id, Workspace.status == "ACTIVE")
            .order_by(Workspace.created_at)
        ).scalars().first()

    with session_scope(factory) as session:
        user = session.get(AppUser, actor_id)

    return TenantSession(
        tenant=TenantSummary(
            id=str(tenant.id),
            name=tenant.name,
            slug=tenant.code,
            timezone=tenant.timezone,
            status=tenant.status,  # type: ignore[arg-type]
        ),
        workspace=WorkspaceSummary(id=str(workspace.id), name=workspace.name),
        user=SessionUser(
            id=str(user.id),
            displayName=user.display_name,
            email=user.email,
            roleLabel=ADMIN_ROLE_LABEL,
            dataScopes=list(ADMIN_DATA_SCOPES),
        ),
        permissions=list(ADMIN_PERMISSIONS),
    )


def _to_content_run(row: ContentRun) -> ContentRunSummary:
    return ContentRunSummary(
        id=row.code,
        title=row.title,
        brand=row.brand,
        stageLabel=row.stage_label,
        statusLabel=row.status_label,
        tone=row.tone,
        owner=row.owner,
        updatedAt=row.updated_at_label,
        allowed_actions=list(row.allowed_actions),
        etag=_etag(row.code, row.row_version),
        version=row.row_version,
    )


def _to_human_task(row: HumanTask) -> HumanTaskSummary:
    return HumanTaskSummary(
        id=row.code,
        title=row.title,
        type=row.type,
        reason=row.reason,
        priority=row.priority,  # type: ignore[arg-type]
        brand=row.brand,
        owner=row.owner,
        dueLabel=row.due_label,
        allowed_actions=list(row.allowed_actions),
        etag=_etag(row.code, row.row_version),
        version=row.row_version,
    )


def _to_material(row: Material) -> MaterialSummary:
    return MaterialSummary(
        id=row.code,
        title=row.title,
        summary=row.summary,
        source=row.source,
        type=row.type,
        trustLabel=row.trust_label,
        tone=row.tone,
        updatedAt=row.updated_at_label,
        allowed_actions=list(row.allowed_actions),
        etag=_etag(row.code, row.row_version),
        version=row.row_version,
    )


def list_content_runs(
    factory: SessionFactory, tenant_id: UUID, page: int, page_size: int
) -> Page[ContentRunSummary]:
    with tenant_session_scope(factory, tenant_id) as session:
        total = session.scalar(
            select(func.count()).select_from(ContentRun)
        )
        rows = (
            session.execute(
                select(ContentRun)
                .order_by(ContentRun.seq)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
    return Page(
        items=[_to_content_run(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def get_content_run(
    factory: SessionFactory, tenant_id: UUID, code: str
) -> ContentRunSummary | None:
    with tenant_session_scope(factory, tenant_id) as session:
        row = session.execute(
            select(ContentRun).where(ContentRun.code == code)
        ).scalars().first()
    return _to_content_run(row) if row is not None else None


def list_human_tasks(
    factory: SessionFactory, tenant_id: UUID, page: int, page_size: int
) -> Page[HumanTaskSummary]:
    with tenant_session_scope(factory, tenant_id) as session:
        total = session.scalar(select(func.count()).select_from(HumanTask))
        rows = (
            session.execute(
                select(HumanTask)
                .order_by(HumanTask.seq)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
    return Page(
        items=[_to_human_task(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def get_human_task(
    factory: SessionFactory, tenant_id: UUID, code: str
) -> HumanTaskSummary | None:
    with tenant_session_scope(factory, tenant_id) as session:
        row = session.execute(
            select(HumanTask).where(HumanTask.code == code)
        ).scalars().first()
    return _to_human_task(row) if row is not None else None


def list_materials(
    factory: SessionFactory, tenant_id: UUID, page: int, page_size: int
) -> Page[MaterialSummary]:
    with tenant_session_scope(factory, tenant_id) as session:
        total = session.scalar(select(func.count()).select_from(Material))
        rows = (
            session.execute(
                select(Material)
                .order_by(Material.seq)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
    return Page(
        items=[_to_material(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def get_material(
    factory: SessionFactory, tenant_id: UUID, code: str
) -> MaterialSummary | None:
    with tenant_session_scope(factory, tenant_id) as session:
        row = session.execute(
            select(Material).where(Material.code == code)
        ).scalars().first()
    return _to_material(row) if row is not None else None
