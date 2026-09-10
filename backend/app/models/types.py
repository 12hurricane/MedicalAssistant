"""
Shared SQLAlchemy column types.

Exists to settle one convention: an instant is an aware UTC datetime in Python,
and UTC in the database, on every backend.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """
    The current instant, timezone-aware, in UTC.

    Use this instead of datetime.utcnow(), which returns a *naive* datetime that
    merely happens to hold UTC — the ambiguity this module exists to remove. It is
    also deprecated as of Python 3.12 and emits a DeprecationWarning here.
    """
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """
    A point in time, always stored and returned as aware UTC.

    SQLite ignores ``DateTime(timezone=True)`` entirely: it has no offset storage,
    so it writes the datetime's *wall clock* and drops the offset without
    converting. An aware ``Asia/Kolkata`` value therefore lands as a different
    instant, 5h30m off, and a ``America/New_York`` one lands 4h off the other way.
    Reads then come back naive, so ``utcnow() - row.column`` raises TypeError.
    Postgres does none of this and returns aware values, so the same code changes
    behaviour between the two backends.

    This normalizes both ends instead:

    - On write, the value is converted to UTC. A naive value is *rejected*, not
      assumed to be UTC — assuming is what silently corrupts an instant, and no
      client-facing schema accepts a datetime, so only server-side code can trip
      this and it will trip loudly in testing rather than quietly in production.
    - On read, the value is always aware UTC, whatever the backend handed back.

    Note this applies to instants only. A ``Date`` or ``Time`` column — a dose
    time, a course start date — is deliberately naive local wall clock, because
    "08:00 in the patient's timezone" is not an instant until a date is fixed to it.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(
                f"UTCDateTime expects a datetime, got {type(value).__name__}: {value!r}"
            )
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(
                f"Refusing to store the naive datetime {value!r}: its timezone is "
                f"unknown, so the instant it represents is ambiguous. Use "
                f"app.models.types.utcnow(), or attach the originating timezone."
            )
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            # SQLite has no offset storage; what it hands back is the UTC value
            # written by process_bind_param, so labelling it UTC is not a guess.
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
