"""Role catalogue and RBAC policy resolution rules.

The SQL join itself is covered by the integration suite; these tests pin the
pure rules around it: role normalisation, the built-in permission catalogue,
RBAC-before-job-title precedence, and malformed permission codes.
"""

import pytest

from aipy.modules.authorization.domain.models import Permission
from aipy.modules.authorization.infrastructure.policy_repository import (
    _grants,
    _resolve_codes,
)
from aipy.modules.authorization.infrastructure.role_catalog import (
    ADMIN_PERMISSIONS,
    ADMIN_ROLE,
    DEFAULT_ROLE_CODE,
    EDITOR_PERMISSIONS,
    EDITOR_ROLE,
    VIEWER_PERMISSIONS,
    grants_for_role,
    permissions_for_role,
    resolve_role,
    role_code,
    system_role_seeds,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("admin", "admin"),
        ("租户管理员", "admin"),
        ("编辑", "editor"),
        ("审核员", "reviewer"),
        ("成员", "member"),
        ("  admin  ", "admin"),
        ("不存在的角色", DEFAULT_ROLE_CODE),
        ("", DEFAULT_ROLE_CODE),
        (None, DEFAULT_ROLE_CODE),
    ],
)
def test_role_code_normalises_aliases_and_unknown_values(value: str | None, expected: str) -> None:
    assert role_code(value) == expected


def test_resolve_role_maps_legacy_job_titles() -> None:
    assert resolve_role("租户管理员") == ADMIN_ROLE
    assert resolve_role(None) == DEFAULT_ROLE_CODE


def test_every_builtin_permission_code_is_wellformed() -> None:
    for code, _name, permissions in system_role_seeds():
        assert permissions, f"role {code} has no permissions"
        for permission in permissions:
            Permission(code=permission)  # raises on malformed codes


def test_builtin_roles_are_seeded_with_display_names() -> None:
    seeds = dict((code, name) for code, name, _ in system_role_seeds())

    assert seeds == {
        "admin": "租户管理员",
        "editor": "编辑",
        "reviewer": "审核员",
        "member": "成员",
    }


def test_admin_superset_of_editor_superset_of_viewer() -> None:
    assert set(VIEWER_PERMISSIONS) < set(EDITOR_PERMISSIONS) < set(ADMIN_PERMISSIONS)
    assert "content:assign" in permissions_for_role(ADMIN_ROLE)
    assert "content:assign" not in permissions_for_role(EDITOR_ROLE)


def test_grants_for_role_returns_permission_objects() -> None:
    grants = grants_for_role("审核员")

    assert all(isinstance(grant, Permission) for grant in grants)
    assert {grant.code for grant in grants} == set(permissions_for_role("reviewer"))


def test_assigned_roles_win_over_job_title() -> None:
    """A tenant-managed role must not be silently overridden by job_title."""

    codes = _resolve_codes(("content:view",), "租户管理员")

    assert codes == ("content:view",)


def test_missing_role_assignment_falls_back_to_job_title() -> None:
    assert _resolve_codes((), "编辑") == EDITOR_PERMISSIONS
    assert _resolve_codes((), None) == VIEWER_PERMISSIONS


def test_grants_drop_duplicates_and_malformed_codes() -> None:
    grants = _grants(("content:view", "content:view", "not-a-permission", "source:edit"))

    assert [grant.permission.code for grant in grants] == ["content:view", "source:edit"]
