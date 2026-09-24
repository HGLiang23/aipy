"""PostgreSQL-backed repositories for the /api/v1 surface.

These replace the in-memory seed with real SQLAlchemy queries. Every tenant-scoped
read/write goes through ``tenant_session_scope`` so Row-Level Security isolates
data by ``app.tenant_id``. The contract (returned schema models) is unchanged,
so routers and the frontend are unaffected.
"""

from uuid import UUID, uuid4

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aipy.modules.content.models import ContentRun, HumanTask, Material
from aipy.modules.identity.domain.models import TokenSubject
from aipy.modules.identity.infrastructure.passwords import PwdlibPasswordHasher
from aipy.modules.organization.models import AppUser, TenantMembership
from aipy.modules.tenancy.models import Tenant
from aipy.modules.brand.models import Workspace
from aipy.modules.authorization.models import Role, RolePermission
from aipy.modules.workflow.models import WorkflowTemplate, WorkflowTemplateVersion
from aipy.modules.governance.models import AuditEvent
from aipy.modules.governance.quota_models import QuotaPolicy, QuotaUsageBucket
from aipy.modules.ai_gateway.models import (
    ModelDefinition,
    ModelProvider,
    ModelRouteCandidate,
    ModelRoutePolicy,
    TenantModelCredential,
)
from aipy.modules.ai_gateway.secrets import fingerprint, mask
from aipy.shared.db import SessionFactory, session_scope, set_user_context, tenant_session_scope
from aipy.shared.security.context import ActorType

from .schemas import (
    AuditEventDetail,
    AuditEventSummary,
    ContentRunSummary,
    CreateMemberRequest,
    CreateMemberResponse,
    CreateModelCredentialRequest,
    HumanTaskSummary,
    ModelCatalogItem,
    ModelCredentialSummary,
    ModelProviderSummary,
    ModelRouteCandidateDTO,
    ModelRoutePolicyDetail,
    ModelRoutePolicySummary,
    UpsertModelRoutePolicyRequest,
    MaterialSummary,
    MemberSummary,
    Page,
    PermissionItem,
    QuotaOverview,
    QuotaPolicyDetail,
    QuotaPolicySummary,
    QuotaUsageDTO,
    ResetMemberPasswordResponse,
    RoleDetail,
    RoleSummary,
    SessionUser,
    TenantSession,
    TenantSummary,
    UpdateMemberRequest,
    UpsertQuotaPolicyRequest,
    WorkflowNode,
    WorkflowTemplateDetail,
    WorkflowTemplateSummary,
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


# ── Member repositories ───────────────────────────────────────────

def _to_member(
    membership: TenantMembership,
    user: AppUser | None = None,
    role_name: str | None = None,
) -> MemberSummary:
    if user is None:
        user = membership  # type: ignore[assignment]
    # role_name must be resolved inside the session: the relationship is lazy and
    # accessing it after the session closes raises DetachedInstanceError.
    role_label = role_name or ADMIN_ROLE_LABEL
    return MemberSummary(
        id=str(membership.id),
        displayName=user.display_name,
        email=user.email,
        roleLabel=role_label,
        status=membership.status,  # type: ignore[arg-type]
        jobTitle=membership.job_title,
        joinedAt=membership.joined_at.isoformat() if membership.joined_at else None,
        allowed_actions=["view", "update"] if membership.status == "ACTIVE" else ["view"],
        etag=_etag(str(membership.id), membership.row_version),
        version=membership.row_version,
    )


def list_members(
    factory: SessionFactory, tenant_id: UUID, page: int, page_size: int
) -> Page[MemberSummary]:
    with tenant_session_scope(factory, tenant_id) as session:
        total = session.scalar(select(func.count()).select_from(TenantMembership))
        rows = (
            session.execute(
                select(TenantMembership)
                .order_by(TenantMembership.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        # Batch load users and roles
        user_ids = [r.user_id for r in rows]
        users = (
            session.execute(select(AppUser).where(AppUser.id.in_(user_ids)))
            .scalars()
            .all()
        )
        user_map = {u.id: u for u in users}

        # Resolve role names up front so no lazy load happens after the session closes.
        role_ids = {r.role_id for r in rows if r.role_id is not None}
        role_names: dict[UUID, str] = {}
        if role_ids:
            role_names = {
                rid: rname
                for rid, rname in session.execute(
                    select(Role.id, Role.name).where(Role.id.in_(role_ids))
                ).all()
            }
        member_rows = [
            (r, user_map.get(r.user_id), role_names.get(r.role_id) if r.role_id else None)
            for r in rows
        ]
    return Page(
        items=[_to_member(r, u, rn) for r, u, rn in member_rows],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def get_member(
    factory: SessionFactory, tenant_id: UUID, member_id: UUID
) -> MemberSummary | None:
    with tenant_session_scope(factory, tenant_id) as session:
        membership = session.get(TenantMembership, member_id)
        if membership is None:
            return None
        user = session.get(AppUser, membership.user_id)
        role_name = _resolve_role_name(session, membership.role_id)
    return _to_member(membership, user, role_name)


def _resolve_role_name(session: Session, role_id: UUID | None) -> str | None:
    """Read a role's display name inside the session (avoids post-close lazy load)."""

    if role_id is None:
        return None
    return session.execute(select(Role.name).where(Role.id == role_id)).scalar()


class MemberConflictError(ValueError):
    """A member cannot be created because it conflicts with existing state."""


class MemberStateError(ValueError):
    """The member exists but its current state forbids the requested operation."""


def _generate_initial_password() -> str:
    import secrets

    # token_urlsafe(12) -> 16 url-safe chars, ~72 bits of entropy.
    return secrets.token_urlsafe(12)


def create_member(
    factory: SessionFactory, tenant_id: UUID, data: CreateMemberRequest
) -> CreateMemberResponse:
    """Create a platform account plus its tenant membership, or bind an existing one.

    ``app_user`` is global (email is unique platform-wide), so an email that already
    exists is reused rather than duplicated — ``initialPassword`` is then ``None``
    because the user already has credentials of their own.
    """

    from datetime import datetime, timezone

    email = data.email.strip()
    display_name = data.displayName.strip()
    if not email or not display_name:
        raise ValueError("邮箱与姓名不能为空")

    role_id = UUID(data.role_id)
    with tenant_session_scope(factory, tenant_id) as session:
        # Roles sit behind RLS, so this lookup must run inside the tenant scope.
        if session.execute(select(Role.id).where(Role.id == role_id)).scalar() is None:
            raise ValueError("指定的角色不存在")

        user = (
            session.execute(select(AppUser).where(AppUser.email == email))
            .scalars()
            .first()
        )

        initial_password: str | None = None
        account_created = False
        if user is None:
            initial_password = _generate_initial_password()
            user = AppUser(
                email=email,
                password_hash=PwdlibPasswordHasher().hash(initial_password),
                display_name=display_name,
                status="ACTIVE",
                mfa_enabled=False,
            )
            session.add(user)
            session.flush()
            account_created = True
        else:
            already_here = session.execute(
                select(TenantMembership.id).where(TenantMembership.user_id == user.id)
            ).scalar()
            if already_here is not None:
                raise MemberConflictError("该邮箱已是本租户成员")

        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=user.id,
            role_id=role_id,
            status="ACTIVE",
            job_title=data.job_title,
            joined_at=datetime.now(timezone.utc),
        )
        session.add(membership)
        session.flush()
        summary = _to_member(membership, user, _resolve_role_name(session, role_id))
    return CreateMemberResponse(
        **summary.model_dump(),
        initialPassword=initial_password,
        accountCreated=account_created,
    )


def update_member(
    factory: SessionFactory, tenant_id: UUID, member_id: UUID, data: UpdateMemberRequest
) -> MemberSummary | None:
    with tenant_session_scope(factory, tenant_id) as session:
        membership = session.get(TenantMembership, member_id)
        if membership is None:
            return None
        if data.role_id is not None:
            membership.role_id = UUID(data.role_id)
        if data.status is not None:
            membership.status = data.status
        session.flush()
        user = session.get(AppUser, membership.user_id)
        role_name = _resolve_role_name(session, membership.role_id)
    return _to_member(membership, user, role_name)


def reset_member_password(
    factory: SessionFactory, tenant_id: UUID, member_id: UUID
) -> ResetMemberPasswordResponse | None:
    """Rotate a member's platform account password and return it once.

    ``app_user`` is platform-global, so this rotates the credential the account
    uses everywhere — not just in this tenant. Only ``ACTIVE`` memberships are
    eligible: login requires an ACTIVE membership, so issuing a password to a
    suspended member would hand out something that could not be used.

    Returns ``None`` when the membership does not exist (caller maps to 404).
    """

    with tenant_session_scope(factory, tenant_id) as session:
        membership = session.get(TenantMembership, member_id)
        if membership is None:
            return None
        if membership.status != "ACTIVE":
            raise MemberStateError(
                "该成员当前已停用，无法登录，请先恢复为正常状态再重置密码"
            )
        user = session.get(AppUser, membership.user_id)
        if user is None:
            raise MemberStateError("该成员没有关联的平台账号，无法重置密码")

        new_password = _generate_initial_password()
        user.password_hash = PwdlibPasswordHasher().hash(new_password)
        session.flush()
        display_name = user.display_name or user.email
        email = user.email

    return ResetMemberPasswordResponse(
        memberId=str(member_id),
        displayName=display_name,
        email=email,
        password=new_password,
    )


# ── Role repositories ──────────────────────────────────────────────

def _to_role_summary(role: Role) -> RoleSummary:
    return RoleSummary(
        id=str(role.id),
        code=role.code,
        name=role.name,
        description=role.description,
        isBuiltin=role.is_builtin,
        isDefault=role.is_default,
        permissionCount=len(role.permissions) if role.permissions else 0,
    )


def _to_role_detail(role: Role, member_count: int = 0) -> RoleDetail:
    return RoleDetail(
        id=str(role.id),
        code=role.code,
        name=role.name,
        description=role.description,
        isBuiltin=role.is_builtin,
        isDefault=role.is_default,
        permissionCount=len(role.permissions) if role.permissions else 0,
        permissions=[
            PermissionItem(code=p.permission_code, dataScope=p.data_scope)
            for p in (role.permissions or [])
        ],
        memberCount=member_count,
    )


def _current_member_count(session: Session, role_id: UUID) -> int:
    """Count members on a role inside the session (``memberships`` is lazy-loaded)."""

    return int(
        session.scalar(
            select(func.count())
            .select_from(TenantMembership)
            .where(TenantMembership.role_id == role_id)
        )
        or 0
    )


def list_roles(factory: SessionFactory, tenant_id: UUID) -> list[RoleSummary]:
    with tenant_session_scope(factory, tenant_id) as session:
        roles = session.execute(
            select(Role).order_by(Role.is_builtin.desc(), Role.code)
        ).scalars().all()
    return [_to_role_summary(r) for r in roles]


def get_role(factory: SessionFactory, tenant_id: UUID, role_id: UUID) -> RoleDetail | None:
    with tenant_session_scope(factory, tenant_id) as session:
        role = session.get(Role, role_id)
        if role is None:
            return None
        member_count = _current_member_count(session, role_id)
    return _to_role_detail(role, member_count)


def update_role(
    factory: SessionFactory, tenant_id: UUID, role_id: UUID, name: str | None,
    description: str | None, permissions: list[PermissionItem] | None,
) -> RoleDetail | None:
    with tenant_session_scope(factory, tenant_id) as session:
        role = session.get(Role, role_id)
        if role is None:
            return None
        if name is not None:
            role.name = name
        if description is not None:
            role.description = description
        if permissions is not None:
            # Replace all permissions
            session.execute(
                __import__("sqlalchemy", fromlist=["delete"]).delete(RolePermission)
                .where(RolePermission.role_id == role_id)
            )
            for p in permissions:
                session.add(RolePermission(
                    role_id=role_id,
                    permission_code=p.code,
                    data_scope=p.dataScope,
                ))
        session.flush()
        session.refresh(role)
        member_count = _current_member_count(session, role_id)
    return _to_role_detail(role, member_count)


# ── Workflow template repositories ────────────────────────────────

def _to_template_summary(tpl: WorkflowTemplate, version: WorkflowTemplateVersion | None) -> WorkflowTemplateSummary:
    return WorkflowTemplateSummary(
        id=str(tpl.id),
        code=tpl.code,
        name=tpl.name,
        category=tpl.category,
        status=tpl.status,
        description=tpl.description,
        nodeCount=len(version.nodes) if version and version.nodes else 0,
        currentVersion=version.version_no if version else None,
        allowed_actions=["view", "publish"] if tpl.category == "TENANT" and tpl.status == "DRAFT" else ["view"],
        etag=_etag(str(tpl.id), tpl.row_version),
        version=tpl.row_version,
    )


def _to_template_detail(tpl: WorkflowTemplate, version: WorkflowTemplateVersion | None) -> WorkflowTemplateDetail:
    summary = _to_template_summary(tpl, version)
    nodes = [
        WorkflowNode(
            node_key=n.get("node_key", ""),
            node_type=n.get("node_type", ""),
            title=n.get("title", ""),
            execution_mode=n.get("execution_mode", ""),
            sequence_no=n.get("sequence_no", 0),
            max_attempts=n.get("max_attempts", 1),
            quality_threshold=n.get("quality_threshold"),
            timeout_seconds=n.get("timeout_seconds"),
        )
        for n in (version.nodes or [])
    ]
    return WorkflowTemplateDetail(**summary.model_dump(), nodes=nodes, policy=version.policy if version else None)


def _current_version(session: Session, tpl: WorkflowTemplate) -> WorkflowTemplateVersion | None:
    if tpl.current_version_id is None:
        return None
    return session.get(WorkflowTemplateVersion, tpl.current_version_id)


def list_workflow_templates(
    factory: SessionFactory, tenant_id: UUID, page: int, page_size: int
) -> Page[WorkflowTemplateSummary]:
    with tenant_session_scope(factory, tenant_id) as session:
        total = session.scalar(select(func.count()).select_from(WorkflowTemplate))
        rows = (
            session.execute(
                select(WorkflowTemplate)
                .order_by(WorkflowTemplate.category, WorkflowTemplate.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        summaries = []
        for tpl in rows:
            version = _current_version(session, tpl)
            summaries.append(_to_template_summary(tpl, version))
    return Page(items=summaries, page=page, page_size=page_size, total=total or 0)


def get_workflow_template(
    factory: SessionFactory, tenant_id: UUID, template_id: UUID
) -> WorkflowTemplateDetail | None:
    with tenant_session_scope(factory, tenant_id) as session:
        tpl = session.get(WorkflowTemplate, template_id)
        if tpl is None:
            return None
        version = _current_version(session, tpl)
    return _to_template_detail(tpl, version)


def publish_workflow_template(
    factory: SessionFactory, tenant_id: UUID, template_id: UUID
) -> WorkflowTemplateDetail | None:
    with tenant_session_scope(factory, tenant_id) as session:
        tpl = session.get(WorkflowTemplate, template_id)
        if tpl is None:
            return None
        # Publish the open DRAFT version if one exists; otherwise this is a no-op
        # that returns the current published detail (re-publish not supported in MVP).
        draft = session.execute(
            select(WorkflowTemplateVersion)
            .where(WorkflowTemplateVersion.template_id == tpl.id, WorkflowTemplateVersion.status == "DRAFT")
            .order_by(WorkflowTemplateVersion.version_no.desc())
        ).scalars().first()
        if draft is not None:
            draft.status = "PUBLISHED"
            draft.published_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            tpl.current_version_id = draft.id
            tpl.status = "PUBLISHED"
            session.flush()
            version = draft
        else:
            version = _current_version(session, tpl)
        session.refresh(tpl)
    return _to_template_detail(tpl, version)


# ── Audit repositories ────────────────────────────────────────────

def _to_audit_summary(e: AuditEvent) -> AuditEventSummary:
    return AuditEventSummary(
        id=str(e.id),
        occurredAt=e.occurred_at.isoformat() if e.occurred_at else "",
        actorType=e.actor_type,
        actorLabel=e.actor_label,
        action=e.action,
        resourceType=e.resource_type,
        resourceId=e.resource_id,
        result=e.result,
        reason=e.reason,
    )


def _to_audit_detail(e: AuditEvent) -> AuditEventDetail:
    summary = _to_audit_summary(e)
    return AuditEventDetail(
        **summary.model_dump(),
        actorId=str(e.actor_id) if e.actor_id else None,
        resourceVersionId=str(e.resource_version_id) if e.resource_version_id else None,
        requestId=e.request_id,
        traceId=e.trace_id,
        ipHash=e.ip_hash,
        userAgent=e.user_agent,
        beforeData=e.before_data,
        afterData=e.after_data,
    )


def list_audit_events(
    factory: SessionFactory,
    tenant_id: UUID,
    page: int,
    page_size: int,
    *,
    action: str | None = None,
    resource_type: str | None = None,
    actor_id: UUID | None = None,
    result: str | None = None,
) -> Page[AuditEventSummary]:
    with tenant_session_scope(factory, tenant_id) as session:
        conditions = []
        if action:
            conditions.append(AuditEvent.action == action)
        if resource_type:
            conditions.append(AuditEvent.resource_type == resource_type)
        if actor_id:
            conditions.append(AuditEvent.actor_id == actor_id)
        if result:
            conditions.append(AuditEvent.result == result)

        count_stmt = select(func.count()).select_from(AuditEvent)
        query_stmt = select(AuditEvent).order_by(AuditEvent.occurred_at.desc())
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
            query_stmt = query_stmt.where(cond)

        total = session.scalar(count_stmt)
        rows = (
            session.execute(query_stmt.offset((page - 1) * page_size).limit(page_size))
            .scalars()
            .all()
        )
    return Page(
        items=[_to_audit_summary(e) for e in rows],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def get_audit_event(
    factory: SessionFactory, tenant_id: UUID, event_id: UUID
) -> AuditEventDetail | None:
    with tenant_session_scope(factory, tenant_id) as session:
        event = session.get(AuditEvent, event_id)
    return _to_audit_detail(event) if event is not None else None


def record_audit(
    factory: SessionFactory,
    tenant_id: UUID,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor_id: UUID | None = None,
    actor_label: str | None = None,
    actor_type: str = "USER",
    result: str = "SUCCESS",
    reason: str | None = None,
    before_data: dict | None = None,
    after_data: dict | None = None,
    metadata: dict | None = None,
) -> None:
    """Append a single audit event. Insert-only by design (see the DB trigger)."""

    with tenant_session_scope(factory, tenant_id) as session:
        session.add(
            AuditEvent(
                tenant_id=tenant_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_id=actor_id,
                actor_label=actor_label,
                actor_type=actor_type,
                result=result,
                reason=reason,
                before_data=before_data,
                after_data=after_data,
                metadata_=metadata,
            )
        )


# ── Model catalog & credential repositories ───────────────────────

def list_model_providers(factory: SessionFactory) -> list[ModelProviderSummary]:
    with session_scope(factory) as session:
        rows = session.execute(
            select(ModelProvider).where(ModelProvider.status == "ACTIVE").order_by(ModelProvider.code)
        ).scalars().all()
    return [
        ModelProviderSummary(
            id=str(p.id), code=p.code, name=p.name, apiStyle=p.api_style, baseUrl=p.base_url
        )
        for p in rows
    ]


def list_model_catalog(factory: SessionFactory) -> list[ModelCatalogItem]:
    with session_scope(factory) as session:
        rows = session.execute(
            select(ModelDefinition, ModelProvider)
            .join(ModelProvider, ModelProvider.id == ModelDefinition.provider_id)
            .where(ModelDefinition.status == "ACTIVE")
            .order_by(ModelProvider.code, ModelDefinition.model_code)
        ).all()
    return [
        ModelCatalogItem(
            id=str(m.id),
            providerId=str(p.id),
            providerCode=p.code,
            modelCode=m.model_code,
            displayName=m.display_name,
            capabilityType=m.capability_type,
            contextWindow=m.context_window,
            supportsStructuredOutput=m.supports_structured_output,
            inputPricePerMillion=float(m.input_price_per_million),
            outputPricePerMillion=float(m.output_price_per_million),
            currencyCode=m.currency_code,
        )
        for m, p in rows
    ]


def _to_credential(c: TenantModelCredential, provider_name: str) -> ModelCredentialSummary:
    return ModelCredentialSummary(
        id=str(c.id),
        providerId=str(c.provider_id),
        providerName=provider_name,
        name=c.name,
        ownershipType=c.ownership_type,
        secretMasked=c.secret_masked,
        status=c.status,
        lastVerifiedAt=c.last_verified_at.isoformat() if c.last_verified_at else None,
        lastVerifyMessage=c.last_verify_message,
        allowed_actions=["test", "revoke"] if c.status != "REVOKED" else ["view"],
        etag=_etag(str(c.id), c.row_version),
        version=c.row_version,
    )


def list_model_credentials(
    factory: SessionFactory, tenant_id: UUID, page: int, page_size: int
) -> Page[ModelCredentialSummary]:
    with tenant_session_scope(factory, tenant_id) as session:
        total = session.scalar(select(func.count()).select_from(TenantModelCredential))
        rows = (
            session.execute(
                select(TenantModelCredential)
                .order_by(TenantModelCredential.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        provider_ids = [r.provider_id for r in rows]
        providers = (
            session.execute(select(ModelProvider).where(ModelProvider.id.in_(provider_ids)))
            .scalars()
            .all()
        )
        provider_map = {p.id: p.name for p in providers}
    return Page(
        items=[_to_credential(r, provider_map.get(r.provider_id, "")) for r in rows],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def get_model_credential(
    factory: SessionFactory, tenant_id: UUID, credential_id: UUID
) -> ModelCredentialSummary | None:
    with tenant_session_scope(factory, tenant_id) as session:
        cred = session.get(TenantModelCredential, credential_id)
        if cred is None:
            return None
        provider = session.get(ModelProvider, cred.provider_id)
    return _to_credential(cred, provider.name if provider else "")


def create_model_credential(
    factory: SessionFactory, tenant_id: UUID, data: CreateModelCredentialRequest
) -> ModelCredentialSummary | None:
    """Create a credential. The raw secret is masked + fingerprinted, never stored."""

    with tenant_session_scope(factory, tenant_id) as session:
        provider = session.get(ModelProvider, UUID(data.provider_id))
        if provider is None:
            return None
        secret = (data.secret or "").strip()
        if not secret:
            raise ValueError("secret is required")
        cred = TenantModelCredential(
            tenant_id=tenant_id,
            provider_id=provider.id,
            name=data.name,
            ownership_type=data.ownership_type,
            secret_masked=mask(secret),
            secret_fingerprint=fingerprint(secret),
            status="ACTIVE",
        )
        session.add(cred)
        session.flush()
        session.refresh(cred)
        provider_name = provider.name
    return _to_credential(cred, provider_name)


def verify_model_credential(
    factory: SessionFactory, tenant_id: UUID, credential_id: UUID
) -> ModelCredentialSummary | None:
    """Server-side verify. In this MVP we record a check timestamp and result.

    A production implementation would make a minimal upstream call; here we only
    assert the stored fingerprint is present (the secret itself was never kept).
    """

    from datetime import datetime, timezone

    with tenant_session_scope(factory, tenant_id) as session:
        cred = session.get(TenantModelCredential, credential_id)
        if cred is None:
            return None
        ok = bool(cred.secret_fingerprint) and cred.status != "REVOKED"
        cred.last_verified_at = datetime.now(timezone.utc)
        cred.last_verify_message = "连接测试通过" if ok else "凭证已吊销，无法验证"
        if not ok:
            cred.status = "INVALID"
        session.flush()
        provider = session.get(ModelProvider, cred.provider_id)
        provider_name = provider.name if provider else ""
    return _to_credential(cred, provider_name)


def revoke_model_credential(
    factory: SessionFactory, tenant_id: UUID, credential_id: UUID
) -> bool:
    with tenant_session_scope(factory, tenant_id) as session:
        cred = session.get(TenantModelCredential, credential_id)
        if cred is None:
            return False
        cred.status = "REVOKED"
        session.flush()
    return True


# ── Model routing policy repositories ─────────────────────────────

def _to_policy_summary(policy: ModelRoutePolicy, candidate_count: int) -> ModelRoutePolicySummary:
    return ModelRoutePolicySummary(
        id=str(policy.id),
        taskType=policy.task_type,
        name=policy.name,
        dailyCostLimit=float(policy.daily_cost_limit) if policy.daily_cost_limit is not None else None,
        perCallTimeoutSeconds=policy.per_call_timeout_seconds,
        status=policy.status,
        candidateCount=candidate_count,
        allowed_actions=["view", "configure"],
        etag=_etag(str(policy.id), policy.row_version),
        version=policy.row_version,
    )


def _candidates_dto(session: Session, policy_id: UUID) -> list[ModelRouteCandidateDTO]:
    rows = session.execute(
        select(ModelRouteCandidate, ModelDefinition)
        .join(ModelDefinition, ModelDefinition.id == ModelRouteCandidate.model_definition_id)
        .where(ModelRouteCandidate.policy_id == policy_id)
        .order_by(ModelRouteCandidate.priority)
    ).all()
    return [
        ModelRouteCandidateDTO(
            priority=c.priority,
            modelDefinitionId=str(c.model_definition_id),
            modelCode=m.model_code,
            modelDisplayName=m.display_name,
            credentialId=str(c.credential_id) if c.credential_id else None,
            temperature=float(c.temperature),
            maxOutputTokens=c.max_output_tokens,
            allowedForPublish=c.allowed_for_publish,
        )
        for c, m in rows
    ]


def list_model_route_policies(
    factory: SessionFactory, tenant_id: UUID
) -> list[ModelRoutePolicySummary]:
    with tenant_session_scope(factory, tenant_id) as session:
        policies = session.execute(
            select(ModelRoutePolicy).order_by(ModelRoutePolicy.task_type)
        ).scalars().all()
        counts = dict(
            session.execute(
                select(ModelRouteCandidate.policy_id, func.count())
                .group_by(ModelRouteCandidate.policy_id)
            ).all()
        )
    return [_to_policy_summary(p, int(counts.get(p.id, 0))) for p in policies]


def get_model_route_policy(
    factory: SessionFactory, tenant_id: UUID, task_type: str
) -> ModelRoutePolicyDetail | None:
    with tenant_session_scope(factory, tenant_id) as session:
        policy = session.execute(
            select(ModelRoutePolicy).where(ModelRoutePolicy.task_type == task_type)
        ).scalars().first()
        if policy is None:
            return None
        candidates = _candidates_dto(session, policy.id)
        count = len(candidates)
    summary = _to_policy_summary(policy, count)
    return ModelRoutePolicyDetail(**summary.model_dump(), candidates=candidates)


def upsert_model_route_policy(
    factory: SessionFactory, tenant_id: UUID, task_type: str, data: UpsertModelRoutePolicyRequest
) -> ModelRoutePolicyDetail | None:
    """Create or fully replace a routing policy's candidates for a task type."""

    with tenant_session_scope(factory, tenant_id) as session:
        # Validate candidate models exist before mutating anything.
        model_ids = [UUID(c.model_definition_id) for c in data.candidates]
        if model_ids:
            found = set(
                session.execute(
                    select(ModelDefinition.id).where(ModelDefinition.id.in_(model_ids))
                ).scalars().all()
            )
            missing = [str(m) for m in model_ids if m not in found]
            if missing:
                raise ValueError(f"unknown model_definition_id: {missing}")

        policy = session.execute(
            select(ModelRoutePolicy).where(ModelRoutePolicy.task_type == task_type)
        ).scalars().first()
        if policy is None:
            policy = ModelRoutePolicy(
                tenant_id=tenant_id,
                task_type=task_type,
                name=data.name,
                daily_cost_limit=data.daily_cost_limit,
                per_call_timeout_seconds=data.per_call_timeout_seconds,
                status=data.status,
            )
            session.add(policy)
            session.flush()
        else:
            policy.name = data.name
            policy.daily_cost_limit = data.daily_cost_limit
            policy.per_call_timeout_seconds = data.per_call_timeout_seconds
            policy.status = data.status

        # Replace candidates atomically (priority is the stable ordering key).
        deleted = __import__("sqlalchemy", fromlist=["delete"]).delete(ModelRouteCandidate)
        session.execute(deleted.where(ModelRouteCandidate.policy_id == policy.id))
        for idx, cand in enumerate(data.candidates, start=1):
            session.add(
                ModelRouteCandidate(
                    tenant_id=tenant_id,
                    policy_id=policy.id,
                    priority=idx,
                    model_definition_id=UUID(cand.model_definition_id),
                    credential_id=UUID(cand.credential_id) if cand.credential_id else None,
                    temperature=__import__("decimal", fromlist=["Decimal"]).Decimal(str(cand.temperature)),
                    max_output_tokens=cand.max_output_tokens,
                    allowed_for_publish=cand.allowed_for_publish,
                )
            )
        session.flush()
        candidates = _candidates_dto(session, policy.id)
        count = len(candidates)
        session.refresh(policy)
    summary = _to_policy_summary(policy, count)
    return ModelRoutePolicyDetail(**summary.model_dump(), candidates=candidates)


# ── Quota policy repositories ─────────────────────────────────────

QUOTA_METRIC_META: dict[str, tuple[str, str]] = {
    "ARTICLES_GENERATED": ("生成文章数", "篇"),
    "ARTICLES_PUBLISHED": ("发布文章数", "篇"),
    "SOURCES_COLLECTED": ("采集素材数", "条"),
    "INPUT_TOKENS": ("输入 Token", "token"),
    "OUTPUT_TOKENS": ("输出 Token", "token"),
    "AI_COST": ("AI 成本", "元"),
    "MAX_CONCURRENT_RUNS": ("并发工作流上限", "个"),
}

# Metrics whose limits are a concurrent gauge rather than a period-accumulated
# counter. They have no usage bucket, so the UI renders the limit as-is.
_GAUGE_METRICS = {"MAX_CONCURRENT_RUNS"}


def _period_bounds(period_type: str, timezone_name: str) -> tuple[datetime, datetime]:
    """Return the [start, end) UTC bounds of the current period.

    The tenant timezone only decides where a period boundary falls; the stored
    timestamps stay UTC.
    """

    from datetime import datetime, time, timedelta, timezone

    try:
        from zoneinfo import ZoneInfo
        local_now = datetime.now(ZoneInfo(timezone_name))
    except Exception:  # unknown tz -> fall back to UTC
        local_now = datetime.now(timezone.utc)

    if period_type == "DAILY":
        start_local = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
        end_local = start_local + timedelta(days=1)
    elif period_type == "ROLLING_30D":
        end_local = local_now
        start_local = local_now - timedelta(days=30)
    else:  # MONTHLY
        start_local = datetime.combine(local_now.date().replace(day=1), time.min, tzinfo=local_now.tzinfo)
        end_local = (start_local + timedelta(days=32)).replace(day=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _alert_level(used: Decimal, soft: Decimal | None, hard: Decimal | None) -> str:
    if used <= 0 and soft is None and hard is None:
        return "NO_LIMIT"
    if hard is not None and used >= hard:
        return "EXCEEDED"
    if soft is None and hard is None:
        return "NO_LIMIT"
    if soft is not None and used >= soft:
        return "WARNING"
    if soft is None and hard is not None and used >= hard:
        return "WARNING"
    return "NORMAL"


def _to_quota_summary(policy: QuotaPolicy) -> QuotaPolicySummary:
    label, unit = QUOTA_METRIC_META.get(policy.metric, (policy.metric, ""))
    return QuotaPolicySummary(
        id=str(policy.id),
        metric=policy.metric,
        metricLabel=label,
        unit=unit,
        periodType=policy.period_type,
        softLimit=float(policy.soft_limit) if policy.soft_limit is not None else None,
        hardLimit=float(policy.hard_limit) if policy.hard_limit is not None else None,
        overageAllowed=policy.overage_allowed,
        status=policy.status,
        allowed_actions=["view", "configure"],
        etag=_etag(str(policy.id), policy.row_version),
        version=policy.row_version,
    )


def _usage_dto(
    session: Session, policy: QuotaPolicy, period_start: datetime, period_end: datetime
) -> QuotaUsageDTO:
    if policy.metric in _GAUGE_METRICS:
        # No bucket exists for a concurrency gauge; report zero used.
        return QuotaUsageDTO(used=0.0, reserved=0.0, usageRatio=None, level="NORMAL")

    bucket = session.execute(
        select(QuotaUsageBucket)
        .where(QuotaUsageBucket.metric == policy.metric)
        .where(QuotaUsageBucket.period_start == period_start)
    ).scalars().first()

    used = bucket.used_amount if bucket else Decimal("0")
    reserved = bucket.reserved_amount if bucket else Decimal("0")
    hard = policy.hard_limit
    ratio = float(used / hard) if hard and hard > 0 else None
    return QuotaUsageDTO(
        used=float(used),
        reserved=float(reserved),
        usageRatio=ratio,
        level=_alert_level(used, policy.soft_limit, policy.hard_limit),
        periodStart=period_start.isoformat(),
        periodEnd=period_end.isoformat(),
    )


def list_quota_policies(factory: SessionFactory, tenant_id: UUID) -> list[QuotaPolicyDetail]:
    """Every tenant quota policy with its current-period usage and alert level."""

    with tenant_session_scope(factory, tenant_id) as session:
        policies = session.execute(
            select(QuotaPolicy).order_by(QuotaPolicy.metric)
        ).scalars().all()
        results: list[QuotaPolicyDetail] = []
        for policy in policies:
            start, end = _period_bounds(policy.period_type, policy.timezone)
            usage = _usage_dto(session, policy, start, end)
            summary = _to_quota_summary(policy)
            results.append(QuotaPolicyDetail(**summary.model_dump(), usage=usage))
    return results


def quota_overview(factory: SessionFactory, tenant_id: UUID) -> QuotaOverview:
    """Dashboard counters derived from the same policies the list endpoint returns."""

    from datetime import datetime, timezone

    details = list_quota_policies(factory, tenant_id)
    return QuotaOverview(
        policyCount=len(details),
        activeCount=sum(1 for d in details if d.status == "ACTIVE"),
        warningCount=sum(1 for d in details if d.usage.level == "WARNING"),
        exceededCount=sum(1 for d in details if d.usage.level == "EXCEEDED"),
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )


def get_quota_policy(
    factory: SessionFactory, tenant_id: UUID, metric: str
) -> QuotaPolicyDetail | None:
    with tenant_session_scope(factory, tenant_id) as session:
        policy = session.execute(
            select(QuotaPolicy).where(QuotaPolicy.metric == metric)
        ).scalars().first()
        if policy is None:
            return None
        start, end = _period_bounds(policy.period_type, policy.timezone)
        usage = _usage_dto(session, policy, start, end)
        summary = _to_quota_summary(policy)
    return QuotaPolicyDetail(**summary.model_dump(), usage=usage)


def upsert_quota_policy(
    factory: SessionFactory, tenant_id: UUID, metric: str, data: UpsertQuotaPolicyRequest
) -> QuotaPolicyDetail | None:
    """Create or update the single policy row for ``metric``."""

    if data.soft_limit is None and data.hard_limit is None:
        raise ValueError("soft_limit and hard_limit cannot both be empty")
    if (
        data.soft_limit is not None
        and data.hard_limit is not None
        and data.soft_limit > data.hard_limit
    ):
        raise ValueError("soft_limit cannot exceed hard_limit")
    if metric not in QUOTA_METRIC_META:
        raise ValueError(f"unknown metric: {metric}")

    with tenant_session_scope(factory, tenant_id) as session:
        policy = session.execute(
            select(QuotaPolicy).where(QuotaPolicy.metric == metric)
        ).scalars().first()
        if policy is None:
            policy = QuotaPolicy(tenant_id=tenant_id, metric=metric)
            session.add(policy)
        policy.period_type = data.period_type
        policy.soft_limit = data.soft_limit
        policy.hard_limit = data.hard_limit
        policy.overage_allowed = data.overage_allowed
        policy.status = data.status
        session.flush()
        session.refresh(policy)
        start, end = _period_bounds(policy.period_type, policy.timezone)
        usage = _usage_dto(session, policy, start, end)
        summary = _to_quota_summary(policy)
    return QuotaPolicyDetail(**summary.model_dump(), usage=usage)
