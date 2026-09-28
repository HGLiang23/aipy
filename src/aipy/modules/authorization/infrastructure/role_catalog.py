"""Permission catalogue for the built-in tenant roles.

Permissions are keyed by role *code*, which is what the ``role`` table stores.
The Chinese labels used as ``tenant_membership.job_title`` in the seed stay
supported as aliases so historic data keeps resolving until every membership
carries real ``membership_role`` rows.
"""

from aipy.modules.authorization.domain.models import Permission

VIEWER_PERMISSIONS: tuple[str, ...] = (
    "batch:view",
    "content:view",
    "artifact:view",
    "source:view",
    "workflow:view",
    "review:view",
    "publication:view",
    "model:view",
    "quota:view",
)

EDITOR_PERMISSIONS: tuple[str, ...] = (
    *VIEWER_PERMISSIONS,
    "content:create",
    "content:edit",
    "content:pause",
    "content:resume",
    "content:rerun",
    "content:cancel",
    "content:export",
    "content:collect",
    "artifact:edit",
    "artifact:compare",
    "source:create",
    "source:edit",
    "source:collect",
    "workflow:execute",
    "review:claim",
    "review:submit",
    "review:assign",
    "member:view",
    "publication:preview",
    "publication:export",
)

REVIEWER_PERMISSIONS: tuple[str, ...] = (
    *VIEWER_PERMISSIONS,
    "artifact:compare",
    "review:claim",
    "review:approve",
    "review:reject",
    "review:reassign",
    "review:submit",
)

ADMIN_PERMISSIONS: tuple[str, ...] = (
    *EDITOR_PERMISSIONS,
    *REVIEWER_PERMISSIONS,
    "content:assign",
    "workflow:configure",
    "model:configure",
    "model:credential_manage",
    "quota:configure",
    "member:view",
    "member:manage",
    "role:view",
    "role:manage",
    "audit:view",
)

ADMIN_ROLE = "admin"
EDITOR_ROLE = "editor"
REVIEWER_ROLE = "reviewer"
MEMBER_ROLE = "member"

DEFAULT_ROLE_CODE = MEMBER_ROLE

#: Built-in roles seeded for every tenant, in creation order.
SYSTEM_ROLES: dict[str, tuple[str, ...]] = {
    ADMIN_ROLE: ADMIN_PERMISSIONS,
    EDITOR_ROLE: EDITOR_PERMISSIONS,
    REVIEWER_ROLE: REVIEWER_PERMISSIONS,
    MEMBER_ROLE: VIEWER_PERMISSIONS,
}

#: Display names used when seeding ``role`` rows.
SYSTEM_ROLE_NAMES: dict[str, str] = {
    ADMIN_ROLE: "租户管理员",
    EDITOR_ROLE: "编辑",
    REVIEWER_ROLE: "审核员",
    MEMBER_ROLE: "成员",
}

#: Legacy job-title labels mapped onto role codes.
ROLE_ALIASES: dict[str, str] = {
    "租户管理员": ADMIN_ROLE,
    "编辑": EDITOR_ROLE,
    "审核员": REVIEWER_ROLE,
    "成员": MEMBER_ROLE,
}


def role_code(role: str | None) -> str:
    """Normalise a role code, a legacy job title, or ``None`` to a role code."""

    if not role:
        return DEFAULT_ROLE_CODE
    normalized = role.strip()
    if normalized in SYSTEM_ROLES:
        return normalized
    return ROLE_ALIASES.get(normalized, DEFAULT_ROLE_CODE)


def resolve_role(job_title: str | None) -> str:
    """Map a membership job title onto a built-in role code."""

    return role_code(job_title)


def permissions_for_role(role: str | None) -> tuple[str, ...]:
    return SYSTEM_ROLES.get(role_code(role), SYSTEM_ROLES[DEFAULT_ROLE_CODE])


def grants_for_role(role: str | None) -> tuple[Permission, ...]:
    return tuple(Permission(code=code) for code in permissions_for_role(role))


def system_role_seeds() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """Built-in roles as ``(code, name, permissions)`` triples for seeding."""

    return tuple(
        (code, SYSTEM_ROLE_NAMES[code], permissions) for code, permissions in SYSTEM_ROLES.items()
    )
