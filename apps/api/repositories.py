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
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from aipy.modules.authorization.domain.models import ResourceContext
from aipy.modules.authorization.infrastructure.policy_repository import TENANT_WIDE_SCOPE
from aipy.modules.authorization.infrastructure.role_catalog import (
    permissions_for_role,
    resolve_role,
)
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
from aipy.modules.identity.domain.models import TokenSubject
from aipy.modules.identity.infrastructure.passwords import PwdlibPasswordHasher
from aipy.modules.organization.models import AppUser, TenantMembership
from aipy.modules.tenancy.models import Tenant
from aipy.shared.db import SessionFactory, session_scope, set_user_context, tenant_session_scope
from aipy.shared.security.context import ActorType, TenantContext

from .errors import ActionError
from .schemas import (
    ContentRunCounts,
    ContentRunDetail,
    ContentRunSummary,
    CreateContentRunCommand,
    CreateMaterialCommand,
    ExportSummary,
    HumanTaskCounts,
    HumanTaskSummary,
    MaterialSummary,
    MemberSummary,
    Page,
    SessionUser,
    TenantSession,
    TenantSummary,
    WorkspaceSummary,
)
from .url_import import fetch_metadata

# Resource types must match the ``resource`` half of the permission codes they are
# checked against, otherwise the service denies with RESOURCE_TYPE_MISMATCH.
CONTENT_RESOURCE = "content"
REVIEW_RESOURCE = "review"
SOURCE_RESOURCE = "source"

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
            roleLabel=resolve_role(membership.job_title),
        )
        for membership, user in rows
    ]
