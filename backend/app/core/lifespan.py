import contextlib
from pathlib import Path

from fastapi import FastAPI

from app.database import engine
from app.services.scheduler_service import reminder_scheduler

# backend/ — where alembic.ini lives, two levels up from app/core/
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


async def _assert_schema_at_head() -> None:
    """
    Refuse to start unless the database is migrated up to head.

    This replaced ``Base.metadata.create_all``, which was actively misleading:
    it creates *missing tables* and nothing else. Add a column, change a type,
    add an index or a unique constraint to an existing table and create_all
    reports success while doing none of it — the app then runs against a schema
    that quietly disagrees with the models, and the failure surfaces later as a
    confusing query error rather than at startup.

    Failing here rather than auto-upgrading is deliberate. Running migrations
    implicitly at startup races when more than one worker boots at once, and
    silently applies whatever destructive DDL happens to be pending.
    """
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    expected = set(ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads())

    def _current(sync_conn) -> set[str]:
        return set(MigrationContext.configure(sync_conn).get_current_heads())

    async with engine.connect() as conn:
        current = await conn.run_sync(_current)

    if current == expected:
        print(f"[DB] Schema at head ({', '.join(sorted(expected)) or 'empty'})")
        return

    if not current:
        raise RuntimeError(
            "Database has no Alembic version stamp, so its schema cannot be "
            "trusted to match the models.\n"
            "  - Empty or new database:      alembic upgrade head\n"
            "  - Existing database already matching the models (e.g. built by the "
            "old create_all):  alembic stamp head"
        )

    raise RuntimeError(
        f"Database schema is out of date: at {sorted(current)}, expected "
        f"{sorted(expected)}.\n"
        f"  Run: alembic upgrade head"
    )


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up MedAssist AI...")

    await _assert_schema_at_head()

    reminder_scheduler.start()
    yield
    print("Shutting down MedAssist AI...")
    reminder_scheduler.shutdown()
    await engine.dispose()
