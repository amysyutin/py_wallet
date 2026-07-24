import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

import app.db.models  # noqa: F401  — регистрирует все модели в Base.metadata
from app.core.config import settings
from app.db.base import Base
from app.db.models.snapshot_service import SNAPSHOT_SERVICE_OWNED_TABLE_NAMES

config = context.config

# URL берём из наших Settings (единая точка правды), а не из alembic.ini
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_api_owned_objects(
    schema_item, name: str | None, type_: str, reflected: bool, compare_to
) -> bool:
    """Keep snapshot-service-owned tables out of the API migration history."""
    if type_ == "table" and name in SNAPSHOT_SERVICE_OWNED_TABLE_NAMES:
        return False
    table_name = getattr(getattr(schema_item, "table", None), "name", None)
    return table_name not in SNAPSHOT_SERVICE_OWNED_TABLE_NAMES


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_api_owned_objects,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_api_owned_objects,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
