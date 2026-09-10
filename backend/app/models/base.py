from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.types import UTCDateTime, utcnow

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    """
    created_at / updated_at as aware UTC instants.

    The defaults are applied in Python, not by the database. ``func.now()`` alone
    rendered as SQLite ``CURRENT_TIMESTAMP`` — naive and truncated to whole seconds
    — while on Postgres it returns an aware ``timestamptz``, so the same column
    disagreed with itself across backends and with every Python-side write. The
    Python default also means the value is on the object immediately after add(),
    without a round trip.

    ``server_default`` is kept only as a backstop for rows inserted outside the
    ORM; the Python default takes precedence whenever SQLAlchemy does the insert.
    """

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, onupdate=utcnow, nullable=True
    )
