"""PostgreSQL-backed repositories for the /api/v1 surface.

Every tenant-scoped read/write goes through ``tenant_session_scope`` so Row-Level
Security isolates data by ``app.tenant_id``.

The ``allowed_actions`` exposed to the frontend are no longer a stored column
value: they are computed per row by :class:`AuthorizationService` from the
caller's policy, so a role change takes effect on the next request and a disabled
actor immediately loses every action.

Write actions follow ``docs/02-workflow-state-machine.md``: the caller must send
``If-Match`` with the version it read, the transition is guarded by the state
machine, and the update itself is protected by the ``row_version`` optimistic
lock, so a stale writer gets a conflict instead of overwriting somebody else's
decision.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from aipy.modules.ai_gateway.models import (
    ModelDefinition,
    ModelProvider,
    ModelRouteCandidate,
    ModelRoutePolicy,
    TenantModelCredential,
)
from aipy.modules.ai_gateway.secrets import fingerprint, mask
from aipy.modules.authorization.domain.models import ResourceContext
from aipy.modules.authorization.infrastructure.policy_repository import TENANT_WIDE_SCOPE
from aipy.modules.authorization.infrastructure.role_catalog import (
    permissions_for_role,
    resolve_role,
)
from aipy.modules.authorization.models import Role, RolePermission
from aipy.modules.authorization.service import AuthorizationService
from aipy.modules.brand.models import Workspace
from aipy.modules.content.models import (
    ContentExport,
    ContentRun,
    ContentRunMaterial,
    HumanTask,
    Material,
    MaterialFile,
)
from aipy.modules.content.state_machine import (
    CONTENT_TRANSITIONS,
    TASK_TRANSITIONS,
    content_status_label,
    plan_content_transition,
    plan_task_transition,
    task_status_label,
)
from aipy.modules.governance.models import AuditEvent
from aipy.modules.governance.quota_models import QuotaPolicy, QuotaUsageBucket
from aipy.modules.identity.domain.models import TokenSubject
from aipy.modules.identity.infrastructure.passwords import PwdlibPasswordHasher
from aipy.modules.organization.models import AppUser, TenantMembership
from aipy.modules.tenancy.models import Tenant
from aipy.modules.workflow.models import WorkflowTemplate, WorkflowTemplateVersion
from aipy.shared.db import SessionFactory, session_scope, set_user_context, tenant_session_scope
from aipy.shared.security.context import ActorType, TenantContext

from .errors import ActionError
from .schemas import (
    AuditEventDetail,
    AuditEventSummary,
    ContentRunCounts,
    ContentRunDetail,
    ContentRunSummary,
    CreateContentRunCommand,
    CreateMaterialCommand,
    CreateMemberRequest,
    CreateMemberResponse,
    CreateModelCredentialRequest,
    ExportSummary,
    HumanTaskCounts,
    HumanTaskSummary,
    MaterialSummary,
    MemberSummary,
    ModelCatalogItem,
    ModelCredentialSummary,
    ModelProviderSummary,
    ModelRouteCandidateDTO,
    ModelRoutePolicyDetail,
    ModelRoutePolicySummary,
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
    UpsertModelRoutePolicyRequest,
    UpsertQuotaPolicyRequest,
    WorkflowNode,
    WorkflowTemplateDetail,
    WorkflowTemplateSummary,
    WorkspaceSummary,
)
from .url_import import fetch_metadata

# Resource types must match the ``resource`` half of the permission codes they are
# checked against, otherwise the service denies with RESOURCE_TYPE_MISMATCH.
CONTENT_RESOURCE = "content"
REVIEW_RESOURCE = "review"
SOURCE_RESOURCE = "source"

# Label used when a member's role can't be resolved to a known RBAC role.
ADMIN_ROLE_LABEL = "租户管理员"

# Candidate actions are ordered: the response keeps this order so the UI stays
# stable regardless of the set the service returns.
CANDIDATE_ACTIONS: dict[str, tuple[str, ...]] = {
    CONTENT_RESOURCE: (
        "content:view",
        "content:create",
        "content:edit",
        "content:assign",
        "content:pause",
        "content:resume",
        "content:rerun",
        "content:cancel",
        "content:export",
        "content:collect",
    ),
    REVIEW_RESOURCE: (
        "review:view",
        "review:claim",
        "review:approve",
        "review:reject",
        "review:reassign",
        "review:submit",
        "review:assign",
    ),
    SOURCE_RESOURCE: (
        "source:view",
        "source:create",
        "source:edit",
        "source:collect",
    ),
}

BoardRow = ContentRun | HumanTask | Material

# How long a claimed human task stays assigned to its handler before it can be
# picked up again (docs/02 section 11.2).
CLAIM_LEASE = timedelta(hours=2)

#: Upload cap for one material file. The bytes live in a database column, so this
#: also bounds how large a single row can grow.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

#: Trust label -> badge tone; mirrors the labels the library already renders.
MATERIAL_TRUST_TONES: dict[str, str] = {
    "高可信": "success",
    "官方来源": "info",
    "内部资料": "neutral",
    "待复核": "warning",
}

#: Upload suffix -> the short type label shown on the material card.
UPLOAD_TYPES: dict[str, str] = {
    ".pdf": "PDF",
    ".doc": "DOCX",
    ".docx": "DOCX",
    ".xls": "XLSX",
    ".xlsx": "XLSX",
    ".csv": "CSV",
    ".md": "Markdown",
    ".txt": "文本",
    ".log": "文本",
    ".html": "网页",
    ".htm": "网页",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".png": "图片",
    ".jpg": "图片",
    ".jpeg": "图片",
    ".gif": "图片",
    ".webp": "图片",
    ".zip": "压缩包",
}

#: Suffixes whose bytes are decodable text, and therefore worth previewing as the
#: material's summary instead of the generic "uploaded a file" note.
TEXTUAL_SUFFIXES = frozenset(
    {".txt", ".md", ".csv", ".json", ".html", ".htm", ".log", ".yaml", ".yml"}
)

#: Export format -> the media type used when the artifact is downloaded.
EXPORT_MEDIA_TYPES: dict[str, str] = {
    "markdown": "text/markdown; charset=utf-8",
}

DEFAULT_EXPORT_MEDIA_TYPE = "text/plain; charset=utf-8"

#: Human task statuses that no longer need attention.
CLOSED_TASK_STATUSES = ("COMPLETED", "CANCELLED")

_ETAG_VERSION = re.compile(r"-v(\d+)$")


def _etag(code: str, version: int) -> str:
    return f'"{code}-v{version}"'


# Actions that actually change state under the machine's guard.
SUPPORTED_ACTIONS: dict[str, frozenset[str]] = {
    CONTENT_RESOURCE: frozenset(CONTENT_TRANSITIONS),
    REVIEW_RESOURCE: frozenset(TASK_TRANSITIONS),
}

# Side-effect actions: no state transition, but a real backend effect (persisting
# an export artifact, linking collected materials, or assigning a handler). They
# still require the caller's permission and the optimistic-lock version.
CONTENT_SIDE_EFFECTS = frozenset({"export", "collect"})
REVIEW_SIDE_EFFECTS = frozenset({"assign"})


def ensure_supported(action: str, resource_type: str) -> None:
    if action not in SUPPORTED_ACTIONS[resource_type]:
        raise ActionError(
            400, "unsupported_action", f"'{action}' is not a {resource_type} state action"
        )


def parse_expected_version(if_match: str | None) -> int | None:
    """Read the version out of an ``If-Match`` header, or ``None`` for ``*``.

    Raises :class:`ActionError` when the header is present but unreadable: a
    caller that sends a malformed precondition must be told, not silently served.
    """

    if if_match is None:
        return None
    candidate = if_match.strip()
    if candidate.startswith("W/"):
        candidate = candidate[2:].strip()
    if candidate == "*":
        return None
    candidate = candidate.strip('"')
    match = _ETAG_VERSION.search(candidate)
    if match is None:
        raise ActionError(400, "invalid_precondition", "If-Match does not carry a version")
    return int(match.group(1))


def _require_version(current: int, expected: int | None) -> None:
    if expected is None:
        raise ActionError(428, "precondition_required", "If-Match is required for write actions")
    if expected != current:
        raise ActionError(
            412,
            "version_conflict",
            f"resource changed since version {expected}; current version is {current}",
        )


def _require_permission(
    authorizer: AuthorizationService,
    subject: TenantContext,
    resource_type: str,
    action: str,
    row: BoardRow,
) -> None:
    """Deny with the service's own reason, so the UI can explain the refusal."""

    # ``workflow_state`` is deliberately not sent: the service treats a resource
    # that carries a state as "must be covered by a workflow state rule", and no
    # policy source populates those rules yet. Sending it here would deny every
    # action the board just offered, so state legality is enforced by the state
    # machine instead. Revisit once workflow_state_policies have a real source.
    decision = authorizer.authorize(
        subject,
        f"{resource_type}:{action}",
        ResourceContext(
            tenant_id=subject.tenant_id,
            resource_type=resource_type,
            resource_id=row.id,
            created_by=row.created_by,
            assigned_to=getattr(row, "assignee_id", None),
        ),
    )
    if not decision.allowed:
        reason = decision.denial_reason.value if decision.denial_reason else "forbidden"
        raise ActionError(403, reason.lower(), f"action '{action}' is not allowed")


def _require_create_permission(
    authorizer: AuthorizationService,
    subject: TenantContext,
    resource_type: str,
    action: str,
) -> None:
    """Authorize an action that has no row yet, such as ``content:create``.

    ``ResourceContext.resource_id`` is optional precisely for this case: there is
    nothing to scope the decision to beyond the tenant.
    """

    decision = authorizer.authorize(
        subject,
        f"{resource_type}:{action}",
        ResourceContext(tenant_id=subject.tenant_id, resource_type=resource_type),
    )
    if not decision.allowed:
        reason = decision.denial_reason.value if decision.denial_reason else "forbidden"
        raise ActionError(403, reason.lower(), f"action '{action}' is not allowed")


def _escape_like(value: str) -> str:
    """Neutralise LIKE metacharacters so a typed ``%`` matches a literal percent sign."""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _stamp(moment: datetime) -> str:
    """Format a timestamp for the board. SQLite-less drivers may hand back naive values."""

    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%d %H:%M")


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _text_preview(data: bytes, filename: str) -> str:
    """Decode an uploaded text file into a one-line preview, or return ``""``."""

    if Path(filename).suffix.lower() not in TEXTUAL_SUFFIXES:
        return ""
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    return " ".join(decoded.split())[:280]


@dataclass(frozen=True)
class StoredFile:
    """An uploaded material file, ready to stream back to the caller."""

    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class ExportDownload:
    """An export artifact's downloadable payload."""

    title: str
    format: str
    payload: str


def _flush(session: Session, current: int) -> None:
    """Commit the pending change, turning a lost race into a 409."""

    try:
        session.flush()
    except StaleDataError as exc:
        raise ActionError(
            409, "version_conflict", f"resource changed concurrently; retry from version {current}"
        ) from exc


def _allowed_actions(
    authorizer: AuthorizationService,
    subject: TenantContext,
    resource_type: str,
    row: BoardRow,
) -> list[str]:
    """Return the bare action names the caller may perform on ``row``.

    Permissions are ``resource:action`` codes internally; the frontend contract
    expects the short action (``view``, ``approve``), so only that half is sent.
    """

    candidates = CANDIDATE_ACTIONS[resource_type]
    context = ResourceContext(
        tenant_id=subject.tenant_id,
        resource_type=resource_type,
        resource_id=row.id,
        created_by=row.created_by,
    )
    allowed = authorizer.allowed_actions(subject, candidates, context)
    return [code.split(":", maxsplit=1)[1] for code in candidates if code in allowed]


def authenticate(factory: SessionFactory, email: str, password: str) -> TokenSubject | None:
    """Verify credentials against ``app_user`` and resolve the active tenant.

    ``tenant_membership`` is protected by FORCE ROW LEVEL SECURITY, so the
    membership lookup cannot use the tenant-isolation policy - there is no
    ``app.tenant_id`` yet at login time. Once the password is verified the session
    sets ``app.user_id``, which the permissive self-lookup policy added in migration
    ``20260724_0003`` uses to expose only that user's own membership rows.

    Returns ``None`` for every failure mode (unknown email, bad password, disabled
    or locked account, no active membership) so the caller cannot use the response
    to enumerate which accounts exist.
    """

    with session_scope(factory) as session:
        user = session.execute(select(AppUser).where(AppUser.email == email)).scalars().first()
        if user is None:
            return None
        if user.status != "ACTIVE":
            return None
        if not PwdlibPasswordHasher().verify(password, user.password_hash):
            return None
        set_user_context(session, user.id)
        membership = (
            session.execute(
                select(TenantMembership).where(
                    TenantMembership.user_id == user.id,
                    TenantMembership.status == "ACTIVE",
                )
            )
            .scalars()
            .first()
        )
        if membership is None:
            return None
        user.last_login_at = datetime.now(UTC)
        session.flush()
        return TokenSubject(
            tenant_id=membership.tenant_id,
            actor_id=user.id,
            actor_type=ActorType.USER,
            session_id=uuid4(),
        )


def build_session(factory: SessionFactory, tenant_id: UUID, actor_id: UUID) -> TenantSession | None:
    """Assemble the dashboard session payload, or ``None`` if it cannot be built.

    A tenant without an ACTIVE workspace (or a deleted user) used to raise
    ``AttributeError`` and surface as a 500; callers now get ``None`` and answer 401.
    """

    with tenant_session_scope(factory, tenant_id) as session:
        tenant = session.get(Tenant, tenant_id)
        workspace = (
            session.execute(
                select(Workspace)
                .where(Workspace.tenant_id == tenant_id, Workspace.status == "ACTIVE")
                .order_by(Workspace.created_at)
            )
            .scalars()
            .first()
        )
        membership = (
            session.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == actor_id,
                )
            )
            .scalars()
            .first()
        )

    with session_scope(factory) as session:
        user = session.get(AppUser, actor_id)

    if tenant is None or workspace is None or user is None or membership is None:
        return None

    role = resolve_role(membership.job_title)
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
            roleLabel=role,
            dataScopes=[grant.scope.value for grant in TENANT_WIDE_SCOPE],
        ),
        permissions=list(permissions_for_role(role)),
    )


def _to_content_run(
    row: ContentRun, subject: TenantContext, authorizer: AuthorizationService
) -> ContentRunSummary:
    return ContentRunSummary(
        id=row.code,
        title=row.title,
        brand=row.brand,
        stageLabel=row.stage_label,
        status=row.status,
        statusLabel=row.status_label,
        tone=row.tone,
        owner=row.owner,
        updatedAt=row.updated_at_label,
        allowed_actions=_allowed_actions(authorizer, subject, CONTENT_RESOURCE, row),
        etag=_etag(row.code, row.row_version),
        version=row.row_version,
    )


def _to_human_task(
    row: HumanTask, subject: TenantContext, authorizer: AuthorizationService
) -> HumanTaskSummary:
    return HumanTaskSummary(
        id=row.code,
        title=row.title,
        type=row.type,
        reason=row.reason,
        priority=row.priority,  # type: ignore[arg-type]
        brand=row.brand,
        owner=row.owner,
        dueLabel=row.due_label,
        statusLabel=task_status_label(row.status),
        allowed_actions=_allowed_actions(authorizer, subject, REVIEW_RESOURCE, row),
        etag=_etag(row.code, row.row_version),
        version=row.row_version,
    )


def _to_material(
    row: Material, subject: TenantContext, authorizer: AuthorizationService
) -> MaterialSummary:
    return MaterialSummary(
        id=row.code,
        title=row.title,
        summary=row.summary,
        source=row.source,
        type=row.type,
        trustLabel=row.trust_label,
        tone=row.tone,
        updatedAt=row.updated_at_label,
        allowed_actions=_allowed_actions(authorizer, subject, SOURCE_RESOURCE, row),
        etag=_etag(row.code, row.row_version),
        version=row.row_version,
    )


def list_content_runs(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    page: int,
    page_size: int,
    *,
    query: str | None = None,
    status: str | None = None,
) -> Page[ContentRunSummary]:
    conditions = []
    if query and query.strip():
        pattern = f"%{_escape_like(query.strip())}%"
        conditions.append(
            or_(
                ContentRun.title.ilike(pattern, escape="\\"),
                ContentRun.brand.ilike(pattern, escape="\\"),
                ContentRun.code.ilike(pattern, escape="\\"),
            )
        )
    if status:
        conditions.append(ContentRun.status == status.upper())

    statement = select(ContentRun)
    counter = select(func.count()).select_from(ContentRun)
    if conditions:
        statement = statement.where(*conditions)
        counter = counter.where(*conditions)

    with tenant_session_scope(factory, subject.tenant_id) as session:
        total = session.scalar(counter)
        rows = (
            session.execute(
                statement.order_by(ContentRun.seq).offset((page - 1) * page_size).limit(page_size)
            )
            .scalars()
            .all()
        )
    return Page(
        items=[_to_content_run(r, subject, authorizer) for r in rows],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def get_content_run(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
) -> ContentRunSummary | None:
    with tenant_session_scope(factory, subject.tenant_id) as session:
        row = session.execute(select(ContentRun).where(ContentRun.code == code)).scalars().first()
    if row is None:
        return None
    return _to_content_run(row, subject, authorizer)


def get_content_run_detail(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
) -> ContentRunDetail | None:
    """A single run including the generated body, for the detail page."""

    with tenant_session_scope(factory, subject.tenant_id) as session:
        row = session.execute(select(ContentRun).where(ContentRun.code == code)).scalars().first()
        if row is None:
            return None
        summary = _to_content_run(row, subject, authorizer)
        return ContentRunDetail(**summary.model_dump(), content=row.content)


def content_run_counts(factory: SessionFactory, subject: TenantContext) -> ContentRunCounts:
    """Status totals for the overview page, so its metrics are not hard-coded."""

    with tenant_session_scope(factory, subject.tenant_id) as session:

        def count(*conditions: ColumnElement[bool]) -> int:
            statement = select(func.count()).select_from(ContentRun)
            if conditions:
                statement = statement.where(*conditions)
            return session.scalar(statement) or 0

        return ContentRunCounts(
            running=count(ContentRun.status == "RUNNING"),
            waiting_human=count(ContentRun.status == "WAITING_HUMAN"),
            paused=count(ContentRun.status == "PAUSED"),
            failed=count(ContentRun.status == "FAILED"),
            completed=count(ContentRun.status == "COMPLETED"),
            total=count(),
        )


def create_content_run(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    command: CreateContentRunCommand,
    actor_id: UUID,
) -> ContentRunSummary:
    """Create a run in RUNNING and hand it to the worker.

    ``DRAFT`` is deliberately not used as the starting state: the state machine has
    no DRAFT -> RUNNING transition, so a draft run could never be started by any
    action the board exposes. Creating the row already running matches what the
    "新建任务" button promises.
    """

    _require_create_permission(authorizer, subject, CONTENT_RESOURCE, "create")
    label, tone = content_status_label("RUNNING")

    with tenant_session_scope(factory, subject.tenant_id) as session:
        actor = session.get(AppUser, actor_id)
        seq = (session.scalar(select(func.max(ContentRun.seq))) or 0) + 1
        row = ContentRun(
            tenant_id=subject.tenant_id,
            code=f"CR-{datetime.now(UTC):%Y%m%d}-{seq:03d}",
            seq=seq,
            title=command.title.strip(),
            brand=command.brand.strip(),
            stage_label=command.stageLabel.strip(),
            status="RUNNING",
            status_label=label,
            tone=tone,
            owner=actor.display_name if actor is not None else "未指派",
            updated_at_label="刚刚",
            allowed_actions=[],
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(row)
        _flush(session, 0)
        return _to_content_run(row, subject, authorizer)


def list_human_tasks(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    page: int,
    page_size: int,
    *,
    query: str | None = None,
    status: str | None = None,
    assignee_id: UUID | None = None,
) -> Page[HumanTaskSummary]:
    conditions = []
    if query and query.strip():
        pattern = f"%{_escape_like(query.strip())}%"
        conditions.append(
            or_(
                HumanTask.title.ilike(pattern, escape="\\"),
                HumanTask.brand.ilike(pattern, escape="\\"),
                HumanTask.code.ilike(pattern, escape="\\"),
            )
        )
    if status:
        conditions.append(HumanTask.status == status.upper())
    if assignee_id is not None:
        conditions.append(HumanTask.assignee_id == assignee_id)

    statement = select(HumanTask)
    counter = select(func.count()).select_from(HumanTask)
    if conditions:
        statement = statement.where(*conditions)
        counter = counter.where(*conditions)

    with tenant_session_scope(factory, subject.tenant_id) as session:
        total = session.scalar(counter)
        rows = (
            session.execute(
                statement.order_by(HumanTask.seq).offset((page - 1) * page_size).limit(page_size)
            )
            .scalars()
            .all()
        )
    return Page(
        items=[_to_human_task(r, subject, authorizer) for r in rows],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def human_task_counts(
    factory: SessionFactory, subject: TenantContext, actor_id: UUID
) -> HumanTaskCounts:
    """Per-tab totals for the human task board, so the badges stop being hard-coded."""

    with tenant_session_scope(factory, subject.tenant_id) as session:

        def count(*conditions: ColumnElement[bool]) -> int:
            statement = select(func.count()).select_from(HumanTask)
            if conditions:
                statement = statement.where(*conditions)
            return session.scalar(statement) or 0

        mine = count(
            HumanTask.assignee_id == actor_id,
            HumanTask.status.notin_(CLOSED_TASK_STATUSES),
        )
        return HumanTaskCounts(
            mine=mine,
            open=count(HumanTask.status == "OPEN"),
            team=count(),
            completed=count(HumanTask.status == "COMPLETED"),
            pending=count(HumanTask.status.notin_(CLOSED_TASK_STATUSES)),
        )


def get_human_task(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
) -> HumanTaskSummary | None:
    with tenant_session_scope(factory, subject.tenant_id) as session:
        row = session.execute(select(HumanTask).where(HumanTask.code == code)).scalars().first()
    if row is None:
        return None
    return _to_human_task(row, subject, authorizer)


def list_materials(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    page: int,
    page_size: int,
    *,
    query: str | None = None,
    type_: str | None = None,
) -> Page[MaterialSummary]:
    conditions = []
    if query and query.strip():
        pattern = f"%{_escape_like(query.strip())}%"
        conditions.append(
            or_(
                Material.title.ilike(pattern, escape="\\"),
                Material.source.ilike(pattern, escape="\\"),
                Material.summary.ilike(pattern, escape="\\"),
            )
        )
    if type_ and type_.strip():
        conditions.append(Material.type == type_.strip())

    statement = select(Material)
    counter = select(func.count()).select_from(Material)
    if conditions:
        statement = statement.where(*conditions)
        counter = counter.where(*conditions)

    with tenant_session_scope(factory, subject.tenant_id) as session:
        total = session.scalar(counter)
        rows = (
            session.execute(
                statement.order_by(Material.seq).offset((page - 1) * page_size).limit(page_size)
            )
            .scalars()
            .all()
        )
    return Page(
        items=[_to_material(r, subject, authorizer) for r in rows],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def get_material(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
) -> MaterialSummary | None:
    with tenant_session_scope(factory, subject.tenant_id) as session:
        row = session.execute(select(Material).where(Material.code == code)).scalars().first()
    if row is None:
        return None
    return _to_material(row, subject, authorizer)


def _material_row(
    *,
    tenant_id: UUID,
    code: str,
    seq: int,
    title: str,
    summary: str,
    source: str,
    type_: str,
    trust_label: str,
    actor_id: UUID,
) -> Material:
    return Material(
        tenant_id=tenant_id,
        code=code,
        seq=seq,
        title=title[:255],
        summary=summary,
        source=source[:255],
        type=type_[:32],
        trust_label=trust_label,
        tone=MATERIAL_TRUST_TONES.get(trust_label, "neutral"),
        updated_at_label="刚刚",
        allowed_actions=[],
        created_by=actor_id,
        updated_by=actor_id,
    )


def create_material(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    command: CreateMaterialCommand,
    actor_id: UUID,
) -> MaterialSummary:
    """Register a source, fetching a URL's title/description when one is given."""

    _require_create_permission(authorizer, subject, SOURCE_RESOURCE, "create")

    url = (command.url or "").strip()
    title = (command.title or "").strip()
    summary = command.summary.strip()
    source = "人工录入"
    type_ = "文本"

    if url:
        # Performed outside the transaction: a slow site must not hold a database
        # connection open, and a failure should surface before any row is written.
        metadata = fetch_metadata(url)
        title = title or metadata.title
        summary = summary or metadata.description or f"来自 {url} 的网页，正文待采集。"
        source = metadata.host
        type_ = "网页"

    title = title or source

    with tenant_session_scope(factory, subject.tenant_id) as session:
        seq = (session.scalar(select(func.max(Material.seq))) or 0) + 1
        row = _material_row(
            tenant_id=subject.tenant_id,
            code=f"MAT-{seq:03d}",
            seq=seq,
            title=title,
            summary=summary,
            source=source,
            type_=type_,
            trust_label=command.trustLabel.strip(),
            actor_id=actor_id,
        )
        session.add(row)
        _flush(session, 0)
        return _to_material(row, subject, authorizer)


def create_uploaded_material(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    title: str,
    trust_label: str,
    actor_id: UUID,
) -> MaterialSummary:
    """Store an uploaded file as the material's original artifact."""

    _require_create_permission(authorizer, subject, SOURCE_RESOURCE, "create")
    if not data:
        raise ActionError(400, "empty_file", "上传的文件为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ActionError(
            413, "file_too_large", f"单个文件不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
        )

    # ``Path.name`` strips any directory component a hostile client put in the header.
    safe_name = Path(filename or "未命名文件").name or "未命名文件"
    resolved_title = title.strip() or Path(safe_name).stem or safe_name
    type_ = UPLOAD_TYPES.get(Path(safe_name).suffix.lower(), "文件")
    preview = _text_preview(data, safe_name)

    with tenant_session_scope(factory, subject.tenant_id) as session:
        seq = (session.scalar(select(func.max(Material.seq))) or 0) + 1
        row = _material_row(
            tenant_id=subject.tenant_id,
            code=f"MAT-{seq:03d}",
            seq=seq,
            title=resolved_title,
            summary=preview or f"人工上传的原件：{safe_name}（{_human_size(len(data))}）。",
            source="人工上传",
            type_=type_,
            trust_label=trust_label.strip(),
            actor_id=actor_id,
        )
        session.add(row)
        session.flush()
        session.add(
            MaterialFile(
                tenant_id=subject.tenant_id,
                material_id=row.id,
                filename=safe_name,
                content_type=content_type or "application/octet-stream",
                byte_size=len(data),
                data=data,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        _flush(session, row.row_version)
        return _to_material(row, subject, authorizer)


def get_material_file(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
) -> StoredFile | None:
    """Return the original bytes of an uploaded material, or ``None`` when absent."""

    with tenant_session_scope(factory, subject.tenant_id) as session:
        material = session.execute(select(Material).where(Material.code == code)).scalars().first()
        if material is None:
            return None
        _require_permission(authorizer, subject, SOURCE_RESOURCE, "view", material)
        row = (
            session.execute(select(MaterialFile).where(MaterialFile.material_id == material.id))
            .scalars()
            .first()
        )
        if row is None:
            return None
        return StoredFile(filename=row.filename, content_type=row.content_type, data=row.data)


def apply_content_action(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
    action: str,
    if_match: str | None,
    actor_id: UUID,
) -> ContentRunSummary:
    """Pause/resume/rerun/cancel a content run, or run a side-effect action."""

    if action in CONTENT_SIDE_EFFECTS:
        return _apply_content_side_effect(
            factory, subject, authorizer, code, action, if_match, actor_id
        )
    ensure_supported(action, CONTENT_RESOURCE)
    expected = parse_expected_version(if_match)

    with tenant_session_scope(factory, subject.tenant_id) as session:
        row = session.execute(select(ContentRun).where(ContentRun.code == code)).scalars().first()
        if row is None:
            raise ActionError(404, "not_found", "content run not found")

        _require_version(row.row_version, expected)
        _require_permission(authorizer, subject, CONTENT_RESOURCE, action, row)
        transition = plan_content_transition(action, row.status)
        if transition is None:
            raise ActionError(
                409,
                "illegal_transition",
                f"cannot {action} a run that is {row.status}",
            )

        row.status = transition.status
        row.status_label = transition.label
        row.tone = transition.tone
        row.updated_by = actor_id
        row.updated_at_label = "刚刚"
        _flush(session, row.row_version)
        return _to_content_run(row, subject, authorizer)


def _build_export_payload(row: ContentRun) -> str:
    """Assemble a portable markdown artifact from the run's metadata and body."""

    header = f"> 品牌：{row.brand}　阶段：{row.stage_label}　状态：{row.status_label}"
    body = row.content or "（本次任务尚未生成正文，仅导出元信息。）"
    return f"# {row.title}\n\n{header}\n\n{body}\n"


def _export_content_run(session: Session, row: ContentRun, actor_id: UUID) -> None:
    """Persist a markdown artifact and stamp the run's last-export time."""

    session.add(
        ContentExport(
            tenant_id=row.tenant_id,
            run_id=row.id,
            run_code=row.code,
            format="markdown",
            title=row.title,
            payload=_build_export_payload(row),
            created_by=actor_id,
        )
    )
    row.exported_at = datetime.now(UTC)


def _collect_materials(session: Session, row: ContentRun, actor_id: UUID) -> None:
    """Link materials whose title/summary mention the run's brand or title."""

    existing = {
        link.material_id
        for link in session.execute(
            select(ContentRunMaterial).where(
                ContentRunMaterial.tenant_id == row.tenant_id,
                ContentRunMaterial.run_id == row.id,
            )
        ).scalars()
    }
    brand = f"%{_escape_like(row.brand)}%"
    title = f"%{_escape_like(row.title)}%"
    conditions = or_(
        Material.title.ilike(brand, escape="\\"),
        Material.summary.ilike(brand, escape="\\"),
        Material.title.ilike(title, escape="\\"),
    )
    matches = (
        session.execute(
            select(Material)
            .where(Material.tenant_id == row.tenant_id, conditions)
            .order_by(Material.seq)
            .limit(10)
        )
        .scalars()
        .all()
    )
    for material in matches:
        if material.id in existing:
            continue
        session.add(
            ContentRunMaterial(
                tenant_id=row.tenant_id,
                run_id=row.id,
                material_id=material.id,
                created_by=actor_id,
            )
        )


def _apply_content_side_effect(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
    action: str,
    if_match: str | None,
    actor_id: UUID,
) -> ContentRunSummary:
    """Run an export/collect side effect without changing the run's status."""

    expected = parse_expected_version(if_match)
    with tenant_session_scope(factory, subject.tenant_id) as session:
        row = session.execute(select(ContentRun).where(ContentRun.code == code)).scalars().first()
        if row is None:
            raise ActionError(404, "not_found", "content run not found")

        _require_version(row.row_version, expected)
        _require_permission(authorizer, subject, CONTENT_RESOURCE, action, row)
        if action == "export":
            _export_content_run(session, row, actor_id)
        elif action == "collect":
            _collect_materials(session, row, actor_id)
        row.updated_by = actor_id
        _flush(session, row.row_version)
        return _to_content_run(row, subject, authorizer)


def list_content_exports(
    factory: SessionFactory, subject: TenantContext, authorizer: AuthorizationService, code: str
) -> list[ExportSummary]:
    """Export history for a run, newest first. Feeds the download panel."""

    with tenant_session_scope(factory, subject.tenant_id) as session:
        run = session.execute(select(ContentRun).where(ContentRun.code == code)).scalars().first()
        if run is None:
            raise ActionError(404, "not_found", "content run not found")
        _require_permission(authorizer, subject, CONTENT_RESOURCE, "export", run)
        rows = (
            session.execute(
                select(ContentExport)
                .where(ContentExport.run_id == run.id)
                .order_by(ContentExport.created_at.desc())
                .limit(50)
            )
            .scalars()
            .all()
        )
        return [
            ExportSummary(
                id=str(row.id),
                title=row.title,
                format=row.format,
                createdAt=_stamp(row.created_at),
                sizeBytes=len(row.payload.encode("utf-8")),
            )
            for row in rows
        ]


def get_content_export(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
    export_id: str,
) -> ExportDownload:
    """Load one export artifact so the route can stream it as a download."""

    try:
        parsed_id = UUID(export_id)
    except ValueError as exc:
        raise ActionError(400, "invalid_id", "导出记录 ID 格式不正确") from exc

    with tenant_session_scope(factory, subject.tenant_id) as session:
        run = session.execute(select(ContentRun).where(ContentRun.code == code)).scalars().first()
        if run is None:
            raise ActionError(404, "not_found", "content run not found")
        _require_permission(authorizer, subject, CONTENT_RESOURCE, "export", run)
        row = (
            session.execute(
                select(ContentExport).where(
                    ContentExport.id == parsed_id, ContentExport.run_id == run.id
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            raise ActionError(404, "not_found", "export artifact not found")
        return ExportDownload(title=row.title, format=row.format, payload=row.payload)


def link_material_to_run(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
    material_code: str,
    actor_id: UUID,
) -> ContentRunSummary:
    """Attach one specific material to a run, from the library's "add" button.

    The ``collect`` action links whatever happens to match; this is the explicit,
    user-chosen counterpart and is idempotent.
    """

    with tenant_session_scope(factory, subject.tenant_id) as session:
        run = session.execute(select(ContentRun).where(ContentRun.code == code)).scalars().first()
        if run is None:
            raise ActionError(404, "not_found", "content run not found")
        material = (
            session.execute(select(Material).where(Material.code == material_code))
            .scalars()
            .first()
        )
        if material is None:
            raise ActionError(404, "not_found", "material not found")

        _require_permission(authorizer, subject, CONTENT_RESOURCE, "collect", run)
        existing = session.scalar(
            select(ContentRunMaterial.id).where(
                ContentRunMaterial.run_id == run.id,
                ContentRunMaterial.material_id == material.id,
            )
        )
        if existing is None:
            session.add(
                ContentRunMaterial(
                    tenant_id=subject.tenant_id,
                    run_id=run.id,
                    material_id=material.id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        run.updated_by = actor_id
        run.updated_at_label = "刚刚"
        _flush(session, run.row_version)
        return _to_content_run(run, subject, authorizer)


def apply_human_task_action(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
    action: str,
    if_match: str | None,
    actor_id: UUID,
    *,
    assignee_id: UUID | None = None,
) -> HumanTaskSummary:
    """Claim, reassign, submit, approve, reject, or assign a human task."""

    if action == "assign":
        return _apply_assign(factory, subject, authorizer, code, assignee_id, if_match, actor_id)
    ensure_supported(action, REVIEW_RESOURCE)
    expected = parse_expected_version(if_match)
    now = datetime.now(UTC)

    with tenant_session_scope(factory, subject.tenant_id) as session:
        row = session.execute(select(HumanTask).where(HumanTask.code == code)).scalars().first()
        if row is None:
            raise ActionError(404, "not_found", "human task not found")

        _require_version(row.row_version, expected)
        _require_permission(authorizer, subject, REVIEW_RESOURCE, action, row)
        transition = plan_task_transition(action, row.status)
        if transition is None:
            raise ActionError(
                409,
                "illegal_transition",
                f"cannot {action} a task that is {row.status}",
            )

        row.status = transition.status
        row.decision = transition.decision
        row.updated_by = actor_id
        if action == "claim":
            row.assignee_id = actor_id
            row.lease_expires_at = now + CLAIM_LEASE
        elif action == "reassign":
            row.assignee_id = assignee_id
            row.lease_expires_at = None if assignee_id is None else now + CLAIM_LEASE
        elif action in {"approve", "reject", "submit"}:
            row.lease_expires_at = None
        _flush(session, row.row_version)
        return _to_human_task(row, subject, authorizer)


def _member_exists(session: Session, tenant_id: UUID, user_id: UUID) -> bool:
    return (
        session.scalar(
            select(TenantMembership.id).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
                TenantMembership.status == "ACTIVE",
            )
        )
        is not None
    )


def _apply_assign(
    factory: SessionFactory,
    subject: TenantContext,
    authorizer: AuthorizationService,
    code: str,
    assignee_id: UUID | None,
    if_match: str | None,
    actor_id: UUID,
) -> HumanTaskSummary:
    """Assign a human task to a named tenant member (claiming it if unclaimed)."""

    if assignee_id is None:
        raise ActionError(400, "invalid_assignee", "assign requires a target member")
    expected = parse_expected_version(if_match)
    now = datetime.now(UTC)

    with tenant_session_scope(factory, subject.tenant_id) as session:
        row = session.execute(select(HumanTask).where(HumanTask.code == code)).scalars().first()
        if row is None:
            raise ActionError(404, "not_found", "human task not found")
        if not _member_exists(session, subject.tenant_id, assignee_id):
            raise ActionError(
                400, "invalid_assignee", "assignee is not an active member of this tenant"
            )

        _require_version(row.row_version, expected)
        _require_permission(authorizer, subject, REVIEW_RESOURCE, "assign", row)
        # Reassignment only means something while the task is still in play. On a
        # COMPLETED/CANCELLED row the writes below would clear the decision and
        # reset the lease while leaving the terminal status in place.
        if row.status not in {"OPEN", "CLAIMED"}:
            raise ActionError(
                409,
                "illegal_transition",
                f"cannot assign a task that is {row.status}",
            )
        row.assignee_id = assignee_id
        if row.status == "OPEN":
            row.status = "CLAIMED"
        row.decision = None
        row.updated_by = actor_id
        row.lease_expires_at = now + CLAIM_LEASE
        _flush(session, row.row_version)
        return _to_human_task(row, subject, authorizer)


def list_members(factory: SessionFactory, subject: TenantContext) -> list[MemberSummary]:
    """Active tenant members, for the assign picker and member directory."""

    with tenant_session_scope(factory, subject.tenant_id) as session:
        rows = session.execute(
            select(TenantMembership, AppUser)
            .join(AppUser, AppUser.id == TenantMembership.user_id)
            .where(
                TenantMembership.tenant_id == subject.tenant_id,
                TenantMembership.status == "ACTIVE",
            )
            .order_by(AppUser.display_name)
        ).all()
    return [
        MemberSummary(
            id=str(membership.user_id),
            displayName=user.display_name,
            email=user.email,
            roleLabel=resolve_role(membership.job_title),
            status=membership.status,
            jobTitle=membership.job_title,
            joinedAt=membership.joined_at.isoformat() if membership.joined_at else None,
            allowed_actions=["view", "update"] if membership.status == "ACTIVE" else ["view"],
            etag=_etag(str(membership.user_id), membership.row_version),
            version=membership.row_version,
        )
        for membership, user in rows
    ]


# ── RBAC admin repositories (from local branch, appended during merge) ───────────

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


def list_members_paged(
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

    from datetime import datetime

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
            joined_at=datetime.now(UTC),
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

    from datetime import datetime

    with tenant_session_scope(factory, tenant_id) as session:
        cred = session.get(TenantModelCredential, credential_id)
        if cred is None:
            return None
        ok = bool(cred.secret_fingerprint) and cred.status != "REVOKED"
        cred.last_verified_at = datetime.now(UTC)
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

    from datetime import datetime, time, timedelta

    try:
        from zoneinfo import ZoneInfo
        local_now = datetime.now(ZoneInfo(timezone_name))
    except Exception:  # unknown tz -> fall back to UTC
        local_now = datetime.now(UTC)

    if period_type == "DAILY":
        start_local = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
        end_local = start_local + timedelta(days=1)
    elif period_type == "ROLLING_30D":
        end_local = local_now
        start_local = local_now - timedelta(days=30)
    else:  # MONTHLY
        start_local = datetime.combine(local_now.date().replace(day=1), time.min, tzinfo=local_now.tzinfo)
        end_local = (start_local + timedelta(days=32)).replace(day=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


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

    from datetime import datetime

    details = list_quota_policies(factory, tenant_id)
    return QuotaOverview(
        policyCount=len(details),
        activeCount=sum(1 for d in details if d.status == "ACTIVE"),
        warningCount=sum(1 for d in details if d.usage.level == "WARNING"),
        exceededCount=sum(1 for d in details if d.usage.level == "EXCEEDED"),
        generatedAt=datetime.now(UTC).isoformat(),
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
