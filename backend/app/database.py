from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# check_same_thread is a SQLite-only connection arg; asyncpg (Postgres) rejects it.
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if is_sqlite else {},
    echo=settings.SQL_ECHO,
)

if is_sqlite:
    # SQLite ignores foreign keys unless asked, and the setting is per-connection.
    # Without this, every ondelete="CASCADE" in the model layer is dead code: rows
    # can point at parents that never existed, and deleting a schedule leaves
    # orphaned reminders that the poller would keep dispatching forever.
    # Postgres enforces FKs natively, so this is SQLite-only.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
