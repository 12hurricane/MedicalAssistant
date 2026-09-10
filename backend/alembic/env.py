"""
Alembic environment for MedAssist AI.

Two things this deliberately does not do:

- It does not read ``sqlalchemy.url`` from alembic.ini. The URL comes from
  ``settings.DATABASE_URL`` (i.e. .env), so migrations and the application can
  never be pointed at different databases.
- It does not import models one by one. ``import app.models`` pulls in every
  model via that package's __init__, so a newly added model cannot be silently
  left out of autogenerate.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import settings
from app.models.base import Base
from app.models.types import UTCDateTime
import app.models  # noqa: F401  registers every table on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# configparser treats % as interpolation, so escape it before handing over a URL
# that might carry a percent-encoded password.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    """
    Teach autogenerate to emit our custom column type.

    Without this, a UTCDateTime column renders as a bare reference Alembic cannot
    import, and the generated migration fails on run. Returning False elsewhere
    means "use the default rendering".
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("import app.models.types")
        return "app.models.types.UTCDateTime()"
    return False


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _configure_kwargs(url: str) -> dict:
    return {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "render_item": render_item,
        # SQLite cannot ALTER most things in place. Batch mode rewrites the table
        # instead, so migrations that alter or drop a column work there at all.
        # Not enabled on Postgres, where it would mean needless table rebuilds.
        "render_as_batch": _is_sqlite(url),
    }


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running against a database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_kwargs(url),
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        **_configure_kwargs(connection.engine.url.render_as_string()),
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
