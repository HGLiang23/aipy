"""Purge data left behind by ``scripts/smoke_admin.py``.

    .venv\\Scripts\\python.exe scripts/cleanup_smoke_data.py

Smoke checks create rows with a ``__smoke__`` marker, and the API deliberately
cannot remove them: members are suspended rather than purged (other tables hold
FKs onto ``tenant_membership``), and credentials are revoked rather than
deleted. So cleanup has to go straight to the database.

Only rows matching the smoke markers are touched. Prefer ``--dry-run`` first.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps"))

from sqlalchemy import delete, select  # noqa: E402

from aipy.modules.ai_gateway.models import ModelRoutePolicy, TenantModelCredential  # noqa: E402
from aipy.modules.organization.models import AppUser, TenantMembership  # noqa: E402
from aipy.shared.db import session_scope, tenant_session_scope  # noqa: E402

MARKER = "__smoke__"
ROUTE_MARKER = "__SMOKE__"
DEMO_TENANT = UUID("019f91e3-0000-4000-8000-000000000001")


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    from apps.api.dependencies import get_session_factory  # noqa: PLC0415

    factory = get_session_factory()
    removed: dict[str, int] = {}

    with tenant_session_scope(factory, DEMO_TENANT) as session:
        # Members: collect the user ids first so the global rows can follow.
        member_rows = session.execute(
            select(TenantMembership.id, TenantMembership.user_id, AppUser.email)
            .join(AppUser, AppUser.id == TenantMembership.user_id)
            .where(AppUser.email.like(f"{MARKER}%"))
        ).all()
        removed["tenant_membership"] = len(member_rows)
        if member_rows and not dry_run:
            session.execute(
                delete(TenantMembership).where(
                    TenantMembership.id.in_([r.id for r in member_rows])
                )
            )

        creds = session.scalar(
            select(TenantModelCredential.id)
            .where(TenantModelCredential.name.like(f"{MARKER}%"))
            .limit(1)
        )
        removed["model_credential"] = 1 if creds else 0
        if creds and not dry_run:
            session.execute(
                delete(TenantModelCredential).where(
                    TenantModelCredential.name.like(f"{MARKER}%")
                )
            )

        route = session.scalar(
            select(ModelRoutePolicy.id).where(ModelRoutePolicy.task_type == ROUTE_MARKER).limit(1)
        )
        removed["model_route_policy"] = 1 if route else 0
        if route and not dry_run:
            session.execute(
                delete(ModelRoutePolicy).where(ModelRoutePolicy.task_type == ROUTE_MARKER)
            )

    # app_user is global (no tenant_id), so it is cleaned outside the tenant scope.
    user_ids = [r.user_id for r in member_rows]
    removed["app_user"] = len(user_ids)
    if user_ids and not dry_run:
        with session_scope(factory) as session:
            session.execute(delete(AppUser).where(AppUser.id.in_(user_ids)))

    for table, count in removed.items():
        print(f"  {table}: {count}")
    print("\nDry run only — nothing was deleted." if dry_run else "\nCleanup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
