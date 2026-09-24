"""Create model provider, model definition, and tenant credential tables.

Revision ID: 20260924_0009_model_credentials
Revises: 20260924_0008_audit_event
Create Date: 2026-09-24 15:00:00
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260924_0009_model_credentials"
down_revision: str | None = "20260924_0008_audit_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity_columns(*, tenant_scoped: bool = False) -> list[SchemaItem]:
    columns: list[SchemaItem] = [sa.Column("id", sa.Uuid(), nullable=False)]
    if tenant_scoped:
        columns.append(sa.Column("tenant_id", sa.Uuid(), nullable=False))
    columns.extend(
        [
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("row_version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        ]
    )
    return columns


PROVIDERS = [
    ("openai-compatible", "OpenAI 兼容", "OPENAI_COMPATIBLE", "https://api.openai.com/v1"),
    ("anthropic", "Anthropic", "ANTHROPIC", "https://api.anthropic.com"),
    ("qwen", "通义千问", "OPENAI_COMPATIBLE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
]


def upgrade() -> None:
    op.create_table(
        "model_provider",
        *_entity_columns(),
        sa.Column("code", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("api_style", sa.String(length=32), nullable=False, server_default=sa.text("'OPENAI_COMPATIBLE'")),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.UniqueConstraint("code", name="uq_model_provider_code"),
    )

    op.create_table(
        "model_definition",
        *_entity_columns(),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey("model_provider.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("model_code", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("capability_type", sa.String(length=32), nullable=False, server_default=sa.text("'CHAT'")),
        sa.Column("context_window", sa.Integer(), nullable=False, server_default=sa.text("8192")),
        sa.Column("supports_structured_output", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("input_price_per_million", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("output_price_per_million", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("currency_code", sa.String(length=8), nullable=False, server_default=sa.text("'CNY'")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.UniqueConstraint("provider_id", "model_code", name="uq_model_definition_provider_code"),
    )
    op.create_index("ix_model_definition_provider", "model_definition", ["provider_id"])

    op.create_table(
        "tenant_model_credential",
        *_entity_columns(tenant_scoped=True),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey("model_provider.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("ownership_type", sa.String(length=16), nullable=False, server_default=sa.text("'BYOK'")),
        sa.Column("secret_masked", sa.String(length=64), nullable=False),
        sa.Column("secret_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("credential_ref", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verify_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("tenant_id", "provider_id", "name", name="uq_tmc_tenant_provider_name"),
    )
    op.create_index("ix_tmc_tenant_provider", "tenant_model_credential", ["tenant_id", "provider_id"])

    # RLS on the tenant-scoped credential table only (provider/catalog are global).
    expression = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    op.execute(sa.text('ALTER TABLE "tenant_model_credential" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE "tenant_model_credential" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            'CREATE POLICY "tmc_tenant_isolation" ON "tenant_model_credential" '
            f"USING ({expression}) WITH CHECK ({expression})"
        )
    )

    # Seed global providers and a few models (no tenant context required).
    bind = op.get_bind()
    provider_ids: dict[str, object] = {}
    for code, name, api_style, base_url in PROVIDERS:
        pid = uuid4()
        provider_ids[code] = pid
        bind.execute(
            sa.text(
                "INSERT INTO model_provider (id, code, name, api_style, base_url, status, created_at, updated_at, row_version) "
                "VALUES (:id, :code, :name, :style, :url, 'ACTIVE', now(), now(), 0)"
            ),
            {"id": pid, "code": code, "name": name, "style": api_style, "url": base_url},
        )

    MODELS = [
        ("openai-compatible", "gpt-4o-mini", "GPT-4o mini", 128000, "0.1500", "0.6000"),
        ("openai-compatible", "gpt-4o", "GPT-4o", 128000, "2.5000", "10.0000"),
        ("anthropic", "claude-3-5-sonnet", "Claude 3.5 Sonnet", 200000, "3.0000", "15.0000"),
        ("qwen", "qwen-plus", "通义千问 Plus", 131072, "0.8000", "2.0000"),
    ]
    for provider_code, model_code, display_name, ctx, in_price, out_price in MODELS:
        bind.execute(
            sa.text(
                "INSERT INTO model_definition "
                "(id, provider_id, model_code, display_name, capability_type, context_window, "
                "supports_structured_output, input_price_per_million, output_price_per_million, "
                "currency_code, status, created_at, updated_at, row_version) "
                "VALUES (:id, :pid, :mcode, :dname, 'CHAT', :ctx, true, :inp, :outp, 'CNY', 'ACTIVE', now(), now(), 0)"
            ),
            {
                "id": uuid4(), "pid": provider_ids[provider_code], "mcode": model_code,
                "dname": display_name, "ctx": ctx, "inp": in_price, "outp": out_price,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_tmc_tenant_provider", table_name="tenant_model_credential")
    op.drop_table("tenant_model_credential")
    op.drop_index("ix_model_definition_provider", table_name="model_definition")
    op.drop_table("model_definition")
    op.drop_table("model_provider")
