"""Restore the tenant foreign keys on the content production tables.

Revision ID: 20260724_0004
Revises: 20260724_0003
Create Date: 2026-09-23

``TenantScopedMixin.tenant_id`` declares ``ForeignKey("tenant.id", ondelete="RESTRICT")``,
so every tenant-owned model expects a real FK constraint. Revision 0002 created the
content tables without it, which left the physical schema out of sync with the model
metadata (``alembic check`` reported three missing foreign keys). This revision closes
that gap for ``content_run``, ``human_task`` and ``material``.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260724_0004"
down_revision: str | None = "20260724_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("content_run", "human_task", "material")


def upgrade() -> None:
    for table in TABLES:
        op.create_foreign_key(
            f"fk_{table}_tenant_id_tenant",
            table,
            "tenant",
            ["tenant_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_constraint(f"fk_{table}_tenant_id_tenant", table, type_="foreignkey")
