"""Alembic environment. Revisions are named NNNN_<slug>.py with revision id = NNNN (NAMING §3).

Create one with: uv run alembic revision --rev-id 0001 -m "identity"
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import seedoc.models  # noqa: F401  # pyright: ignore[reportUnusedImport]  # registers ORM models
from seedoc.config import get_settings
from seedoc.db.base import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = create_async_engine(get_settings().database_owner_url)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=get_settings().database_owner_url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_async_migrations())
