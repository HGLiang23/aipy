"""Alembic environment for the synchronous PostgreSQL data model."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Register mappings for metadata-driven revision checks without coupling model modules.
import aipy.modules.ai_gateway.models  # noqa: F401, E402
import aipy.modules.authorization.models  # noqa: F401, E402
import aipy.modules.brand.models  # noqa: F401, E402
import aipy.modules.content.models  # noqa: F401, E402
import aipy.modules.governance.models  # noqa: F401, E402
import aipy.modules.governance.quota_models  # noqa: F401, E402
import aipy.modules.organization.models  # noqa: F401, E402
import aipy.modules.tenancy.models  # noqa: F401, E402
import aipy.modules.workflow.models  # noqa: F401, E402
from aipy.shared.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("AIPY_DATABASE_URL") or os.getenv("AIPY_DATABASE__URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
