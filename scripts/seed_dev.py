"""Development seed: apply migrations and insert demo data into PostgreSQL.

Run from the project root:

    .venv\\Scripts\\python.exe scripts\\seed_dev.py

This applies all Alembic migrations (``alembic upgrade head``) and then inserts a
demo tenant, workspace, brand, user, and the content/human-task/material rows used
by the UI.

The seed is *per-entity idempotent*: every block checks for its fixed primary key
first and is skipped when already present, so the script can be re-run safely even
if a previous run failed halfway through.

Notes for maintainers:

* ``make_session_factory`` sets ``autoflush=False``, so a row ``add()``-ed in the
  current session is not visible to ``Session.get`` until an explicit ``flush()``.
  Always check existence *before* mutating, or hold on to the ORM object itself.
* ``TenantEntityMixin`` defines ``tenant_id`` but never fills it in, and the tenant
  tables have ``FORCE ROW LEVEL SECURITY`` with a ``WITH CHECK`` clause. Every
  tenant-owned row therefore needs an explicit ``tenant_id`` *and* the
  transaction-local ``app.tenant_id`` context (see ``tenant_session_scope``).
"""

from datetime import UTC, datetime
from pathlib import Path
from subprocess import CalledProcessError, run
from sys import executable, path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
path.insert(0, str(ROOT))

import os

from sqlalchemy import func, select, text

from aipy.modules.authorization.infrastructure.role_catalog import system_role_seeds
from aipy.modules.brand.models import Brand, Workspace
from aipy.modules.content.models import ContentRun, HumanTask, Material
from aipy.modules.identity.infrastructure.passwords import PwdlibPasswordHasher
from aipy.modules.organization.models import (
    AppUser,
    MembershipRole,
    Role,
    RolePermission,
    TenantMembership,
)
from aipy.modules.tenancy.models import Plan, Tenant
from aipy.shared.config import get_settings
from aipy.shared.db import make_engine, make_session_factory, session_scope, tenant_session_scope

TENANT_ID = UUID("019f91e3-0000-4000-8000-000000000001")
WORKSPACE_ID = UUID("019f91e3-0000-4000-8000-000000000002")
USER_ID = UUID("019f91e3-0000-4000-8000-000000000003")
MEMBERSHIP_ID = UUID("019f91e3-0000-4000-8000-000000000004")
PLAN_ID = UUID("019f91e3-0000-4000-8000-000000000005")
BRAND_ID = UUID("019f91e3-0000-4000-8000-000000000006")

# Fixed PKs keep the seed idempotent: admin, editor, reviewer, member.
ROLE_IDS = {
    "admin": UUID("019f91e3-0000-4000-8000-000000000007"),
    "editor": UUID("019f91e3-0000-4000-8000-000000000008"),
    "reviewer": UUID("019f91e3-0000-4000-8000-000000000009"),
    "member": UUID("019f91e3-0000-4000-8000-00000000000a"),
}
DEMO_ROLE_CODES = ("admin",)

DEMO_EMAIL = "editor@example.com"
DEMO_PASSWORD = "demo-password"

# status_label is display text; status is the machine-readable state the state
# machine transitions on. They must agree, or the board shows one thing while the
# API allows another.
STATUS_BY_LABEL = {
    "运行中": "RUNNING",
    "等待人工": "WAITING_HUMAN",
    "已暂停": "PAUSED",
    "已完成": "COMPLETED",
    "需要处理": "FAILED",
    "已取消": "CANCELLED",
}

_CONTENT_RUNS = [
    (
        "CR-20260724-018",
        1,
        "AI 搜索如何改变品牌内容策略",
        "远山商业",
        "分段写作",
        "运行中",
        "info",
        "林编辑",
        "2 分钟前",
        ["view", "pause"],
    ),
    (
        "CR-20260724-017",
        2,
        "周末城市轻徒步路线清单",
        "慢游计划",
        "大纲审核",
        "等待人工",
        "warning",
        "周岚",
        "18 分钟前",
        ["view", "approve", "reject"],
    ),
    (
        "CR-20260724-014",
        3,
        "团队知识库落地的五个误区",
        "远山商业",
        "平台适配",
        "运行中",
        "info",
        "林编辑",
        "42 分钟前",
        ["view", "pause"],
    ),
    (
        "CR-20260724-011",
        4,
        "新消费品牌七月观察",
        "趋势手记",
        "发布包",
        "已完成",
        "success",
        "陈知",
        "今天 09:20",
        ["view", "export"],
    ),
    (
        "CR-20260723-096",
        5,
        "内容团队如何配置模型预算",
        "远山商业",
        "事实检查",
        "需要处理",
        "danger",
        "林编辑",
        "昨天 18:06",
        ["view", "rerun"],
    ),
]

_HUMAN_TASKS = [
    (
        "HT-201",
        1,
        "审核《周末城市轻徒步路线清单》大纲",
        "大纲审核",
        "人机协同模板在大纲节点要求人工确认。",
        "高",
        "慢游计划",
        "已分配给你",
        "今天 14:30 到期",
        ["approve", "reject", "reassign"],
    ),
    (
        "HT-198",
        2,
        "确认新消费品牌观察的引用来源",
        "事实核查",
        "两条行业数据缺少一级来源。",
        "普通",
        "趋势手记",
        "已分配给你",
        "今天 18:00 到期",
        ["submit", "reassign"],
    ),
    (
        "HT-193",
        3,
        "处理模型预算文章的质量门禁",
        "异常处理",
        "事实检查评分 72，低于租户阈值 80。",
        "普通",
        "远山商业",
        "团队任务",
        "明天 10:00 到期",
        ["claim"],
    ),
]

_MATERIALS = [
    (
        "MAT-301",
        1,
        "2026 内容营销趋势报告",
        "聚焦生成式搜索、内容可信度和品牌自有数据策略。",
        "research.example.com",
        "PDF",
        "高可信",
        "success",
        "今天 10:16",
        ["view", "edit"],
    ),
    (
        "MAT-299",
        2,
        "微信公众号内容运营规则更新",
        "平台近期关于原创、转载和 AI 辅助内容标识的规则摘要。",
        "weixin.qq.com",
        "网页",
        "官方来源",
        "info",
        "今天 09:42",
        ["view", "edit"],
    ),
    (
        "MAT-287",
        3,
        "团队访谈：内容审核流程",
        "内部编辑与审核员访谈纪要，包含现有协作问题。",
        "人工上传",
        "DOCX",
        "内部资料",
        "neutral",
        "昨天 16:20",
        ["view", "edit"],
    ),
    (
        "MAT-281",
        4,
        "城市徒步路线用户调研",
        "来自 126 份问卷的偏好、时长和安全关注点汇总。",
        "人工上传",
        "XLSX",
        "待复核",
        "warning",
        "昨天 11:08",
        ["view", "edit"],
    ),
]


def apply_migrations() -> None:
    env = dict(os.environ)
    env["AIPY_DATABASE__URL"] = get_settings().database.url
    print("Applying Alembic migrations (alembic upgrade head)...")
    try:
        run(
            [executable, "-m", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
            cwd=str(ROOT),
            env=env,
            check=True,
        )
    except CalledProcessError as exc:  # pragma: no cover - surfaced to operator
        raise SystemExit(f"alembic upgrade failed: {exc}") from exc


def _ensure_default_roles(session, created: list[str]) -> None:
    """Create the built-in roles with their permissions, once per tenant.

    Roles are keyed by fixed IDs so re-running the seed only fills in the
    permission rows that are missing.
    """

    for code, name, permissions in system_role_seeds():
        role_id = ROLE_IDS[code]
        if session.get(Role, role_id) is None:
            session.add(
                Role(
                    id=role_id,
                    tenant_id=TENANT_ID,
                    code=code,
                    name=name,
                    description=f"{name}（系统预置角色）",
                    is_system=True,
                    status="ACTIVE",
                )
            )
            created.append(f"role:{code}")
            session.flush()

        existing = set(
            session.execute(
                select(RolePermission.permission_code).where(RolePermission.role_id == role_id)
            )
            .scalars()
            .all()
        )
        missing = [permission for permission in permissions if permission not in existing]
        for permission in missing:
            session.add(
                RolePermission(
                    tenant_id=TENANT_ID,
                    role_id=role_id,
                    permission_code=permission,
                )
            )
        if missing:
            created.append(f"role_permission:{code} x{len(missing)}")
            session.flush()


def seed(factory) -> list[str]:
    """Insert demo rows, skipping anything already present. Returns inserted names."""

    created: list[str] = []
    now = datetime.now(UTC)

    # --- global entities (no RLS) -------------------------------------------
    with session_scope(factory) as session:
        if session.get(Plan, PLAN_ID) is None:
            session.add(
                Plan(
                    id=PLAN_ID,
                    code="default",
                    name="默认套餐",
                    status="ACTIVE",
                    max_users=10,
                    max_workspaces=3,
                    max_daily_articles=100,
                )
            )
            created.append("plan")

    with session_scope(factory) as session:
        if session.get(AppUser, USER_ID) is None:
            session.add(
                AppUser(
                    id=USER_ID,
                    email=DEMO_EMAIL,
                    password_hash=PwdlibPasswordHasher().hash(DEMO_PASSWORD),
                    display_name="林编辑",
                    status="ACTIVE",
                    mfa_enabled=False,
                )
            )
            created.append("app_user")

    # --- tenant row: RLS requires the context to be set *before* the insert --
    with factory() as session:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(TENANT_ID)},
        )
        if session.get(Tenant, TENANT_ID) is None:
            session.add(
                Tenant(
                    id=TENANT_ID,
                    code="yuanshan",
                    name="远山内容工作室",
                    status="ACTIVE",
                    timezone="Asia/Shanghai",
                    locale="zh-CN",
                    data_region="CN",
                    plan_id=PLAN_ID,
                )
            )
            created.append("tenant")
        session.commit()

    # --- tenant-owned entities ---------------------------------------------
    # Insert order matters: these mappers have no ORM relationship(), so unit-of-work
    # ordering is not reliable. Flush between steps to make the FK order explicit.
    with tenant_session_scope(factory, TENANT_ID) as session:
        if session.get(TenantMembership, MEMBERSHIP_ID) is None:
            session.add(
                TenantMembership(
                    id=MEMBERSHIP_ID,
                    tenant_id=TENANT_ID,
                    user_id=USER_ID,
                    status="ACTIVE",
                    job_title="租户管理员",
                    joined_at=now,
                )
            )
            created.append("tenant_membership")
        # membership first: workspace.created_by_membership_id references it
        session.flush()

        _ensure_default_roles(session, created)
        for code in DEMO_ROLE_CODES:
            if (
                session.execute(
                    select(MembershipRole).where(
                        MembershipRole.membership_id == MEMBERSHIP_ID,
                        MembershipRole.role_id == ROLE_IDS[code],
                    )
                )
                .scalars()
                .first()
                is None
            ):
                session.add(
                    MembershipRole(
                        tenant_id=TENANT_ID,
                        membership_id=MEMBERSHIP_ID,
                        role_id=ROLE_IDS[code],
                    )
                )
                created.append(f"membership_role:{code}")
        session.flush()

        workspace = session.get(Workspace, WORKSPACE_ID)
        if workspace is None:
            workspace = Workspace(
                id=WORKSPACE_ID,
                tenant_id=TENANT_ID,
                code="default",
                name="默认工作空间",
                status="ACTIVE",
                created_by_membership_id=MEMBERSHIP_ID,
            )
            session.add(workspace)
            created.append("workspace")
        # workspace first: brand.workspace_id references it
        session.flush()

        if session.get(Brand, BRAND_ID) is None:
            session.add(
                Brand(
                    id=BRAND_ID,
                    tenant_id=TENANT_ID,
                    workspace_id=WORKSPACE_ID,
                    name="远山商业",
                    description="远山内容工作室主品牌",
                    prohibited_terms=[],
                    default_language="zh-CN",
                    status="ACTIVE",
                )
            )
            created.append("brand")
        # brand first: workspace.default_brand_id points back at it (circular FK)
        session.flush()

        workspace.default_brand_id = BRAND_ID
        session.flush()

        if not session.execute(select(func.count()).select_from(ContentRun)).scalar():
            for (
                code,
                seq,
                title,
                brand,
                stage,
                status_l,
                tone,
                owner,
                updated,
                actions,
            ) in _CONTENT_RUNS:
                session.add(
                    ContentRun(
                        tenant_id=TENANT_ID,
                        code=code,
                        seq=seq,
                        title=title,
                        brand=brand,
                        stage_label=stage,
                        status_label=status_l,
                        status=STATUS_BY_LABEL.get(status_l, "RUNNING"),
                        tone=tone,
                        owner=owner,
                        updated_at_label=updated,
                        allowed_actions=list(actions),
                    )
                )
            created.append(f"content_run x{len(_CONTENT_RUNS)}")

        if not session.execute(select(func.count()).select_from(HumanTask)).scalar():
            for (
                code,
                seq,
                title,
                type_,
                reason,
                priority,
                brand,
                owner,
                due,
                actions,
            ) in _HUMAN_TASKS:
                session.add(
                    HumanTask(
                        tenant_id=TENANT_ID,
                        code=code,
                        seq=seq,
                        title=title,
                        type=type_,
                        reason=reason,
                        priority=priority,
                        brand=brand,
                        owner=owner,
                        due_label=due,
                        status="CLAIMED" if owner == "已分配给你" else "OPEN",
                        assignee_id=USER_ID if owner == "已分配给你" else None,
                        allowed_actions=list(actions),
                    )
                )
            created.append(f"human_task x{len(_HUMAN_TASKS)}")

        if not session.execute(select(func.count()).select_from(Material)).scalar():
            for (
                code,
                seq,
                title,
                summary,
                source,
                type_,
                trust,
                tone,
                updated,
                actions,
            ) in _MATERIALS:
                session.add(
                    Material(
                        tenant_id=TENANT_ID,
                        code=code,
                        seq=seq,
                        title=title,
                        summary=summary,
                        source=source,
                        type=type_,
                        trust_label=trust,
                        tone=tone,
                        updated_at_label=updated,
                        allowed_actions=list(actions),
                    )
                )
            created.append(f"material x{len(_MATERIALS)}")

    return created


def main() -> None:
    settings = get_settings()
    print(f"Target database: {settings.database.url}")
    apply_migrations()

    factory = make_session_factory(make_engine(settings.database.url))
    created = seed(factory)
    if created:
        print("Seeded: " + ", ".join(created))
    else:
        print("Nothing to do - demo data already present (idempotent).")
    print(f"Done. Demo login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
