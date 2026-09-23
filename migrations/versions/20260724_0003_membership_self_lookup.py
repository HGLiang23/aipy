"""Allow a user to discover their own tenant memberships during login.

Revision ID: 20260724_0003
Revises: 20260724_0002
Create Date: 2026-09-23

Login is a bootstrapping problem for row-level security: to resolve which tenant a
user belongs to we must read ``tenant_membership``, but that table is protected by
its tenant-isolation policy and no ``app.tenant_id`` exists yet.

This revision adds a second (permissive, therefore OR-ed) SELECT policy keyed on a
new ``app.user_id`` GUC. A session that has already verified the user's password may
set ``app.user_id`` and read that user's own memberships.

Safety notes:

* The policy is ``FOR SELECT`` only - it grants no write access.
* The predicate is scoped to ``user_id``, so a session can only ever see the rows of
  the user it has authenticated; the server sets ``app.user_id`` from the verified
  credential and never from client input.
* When ``app.user_id`` is unset, ``current_setting(..., true)`` yields NULL, the
  comparison evaluates to NULL and no rows are returned, so nothing leaks.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0003"
down_revision: str | None = "20260724_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY_NAME = "tenant_membership_self_lookup"


def upgrade() -> None:
    op.execute(
        sa.text(
            f'CREATE POLICY "{POLICY_NAME}" ON "tenant_membership" FOR SELECT '
            "USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "tenant_membership"'))
