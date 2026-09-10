import enum
from datetime import date, time
from typing import List

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ScheduleLifecycle(str, enum.Enum):
    """
    What a schedule row means right now.

    This replaces a boolean ``active`` that was answering four questions at once and
    getting one of them wrong.

    ``active=True`` did not mean "live", it meant "not explicitly retired". A course
    that finished last month kept ``active=True`` forever, because both consumers
    re-filter on the course dates at query time (``get_todays_doses`` and
    ``create_due_reminders``). So the column disagreed with the schedule's own
    ``end_date``, and the column was the one that looked authoritative.

    ``active=False`` was worse, because it collapsed two clinically different facts:

    - a clinician discontinued the medication, or rejected the prescription --- the
      remaining doses were *not meant to be taken*;
    - the row was replaced by a newer schedule for the same medication --- the doses
      logged against it *were* taken correctly.

    Both look identical after the fact. A clinician reviewing a gap in adherence
    cannot tell "the patient was taken off this drug" from "the dose time moved",
    and those lead to opposite conclusions.
    """

    #: Live. Dosing on any local day inside ``[start_date, end_date]``.
    ACTIVE = "ACTIVE"

    #: Ran to the end of its prescribed course. **Derived, never stored** --- see
    #: :meth:`MedicationSchedule.lifecycle_on` and :data:`STORED_SCHEDULE_STATUSES`.
    COMPLETED = "COMPLETED"

    #: Stopped by a clinical decision: the medication was discontinued, or the
    #: prescription was rejected. Doses after this point were not meant to be taken,
    #: so their absence is not non-adherence.
    CANCELLED = "CANCELLED"

    #: Replaced by a newer schedule for the same medication --- a new course start
    #: date, or a corrected frequency that moved the dose times. History logged
    #: against this row remains valid; it is simply no longer the current plan.
    SUPERSEDED = "SUPERSEDED"


#: The statuses the column is allowed to hold.
#:
#: COMPLETED is deliberately absent. Storing it would require something to notice the
#: day a course ends and write the row --- a scheduled job that can fail, be forgotten,
#: or run in the wrong timezone, leaving the column stale in exactly the way ``active``
#: already was. Deriving it from ``end_date`` cannot go stale, needs no job, and makes
#: extending a course revive the schedule automatically instead of requiring a second
#: write to undo a status that was only ever a cached calculation.
STORED_SCHEDULE_STATUSES: frozenset[str] = frozenset(
    {
        ScheduleLifecycle.ACTIVE.value,
        ScheduleLifecycle.CANCELLED.value,
        ScheduleLifecycle.SUPERSEDED.value,
    }
)

# Rendered from the frozenset above rather than typed out, so the constraint and the
# Python vocabulary cannot drift apart. Sorted for a deterministic DDL string.
_STORED_STATUS_SQL = ", ".join(f"'{value}'" for value in sorted(STORED_SCHEDULE_STATUSES))


class MedicationSchedule(TimestampMixin, Base):
    __tablename__ = "medication_schedules"
    __table_args__ = (
        # Prevents re-running schedule generation from double-booking a dose
        # (which would fire duplicate reminders). start_date is included so a
        # genuinely new course of the same medication is still allowed.
        UniqueConstraint(
            "prescribed_medication_id", "scheduled_time", "start_date",
            name="uq_schedule_med_time_start",
        ),
        # The database refuses a stored COMPLETED, so "derived, never stored" is a
        # guarantee rather than a convention someone has to remember. Without this,
        # the first person to write `status="COMPLETED"` gets a row that silently
        # stops dosing and never comes back when the course is extended.
        CheckConstraint(
            f"status IN ({_STORED_STATUS_SQL})",
            name="ck_schedule_status_stored",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prescribed_medication_id: Mapped[int] = mapped_column(
        ForeignKey("prescribed_medications.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    scheduled_time: Mapped[time] = mapped_column(Time, nullable=False)
    relation_to_meal: Mapped[str | None] = mapped_column(String(30), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: One of :data:`STORED_SCHEDULE_STATUSES`. Read it through
    #: :meth:`lifecycle_on` when the question is "is this dosing today", because the
    #: stored value alone cannot answer that.
    #:
    #: No server default: ``alembic/env.py`` runs with ``compare_server_default=True``,
    #: so a default in the database that the model does not declare is a permanent
    #: ``alembic check`` diff. The Python-side default covers every ORM insert, and the
    #: migration backfills the rows that predate the column.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ScheduleLifecycle.ACTIVE.value,
    )

    # Relationships
    prescribed_medication: Mapped["PrescribedMedication"] = relationship("PrescribedMedication", back_populates="schedules")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="schedules")

    # medication_events is the patient's adherence history: what they took, what they
    # missed, and why. It is the evidence a clinician reviews and the only input to the
    # adherence score. It is not derived from anything, so a deleted event is gone.
    #
    # The FK on medication_events.schedule_id is therefore ON DELETE RESTRICT, and this
    # relationship carries no cascade and no delete-orphan. The database is the single
    # authority on whether a dose record may go, and it refuses.
    #
    # What that buys, concretely:
    #
    #   db.delete(schedule)     -> IntegrityError from the RESTRICT, history intact.
    #                              passive_deletes="all" is what makes this reach the
    #                              database at all: it stops SQLAlchemy pre-emptively
    #                              NULLing the children's FK on a parent delete, which
    #                              would otherwise fail on its own NOT NULL and never
    #                              let the real constraint speak.
    #   schedule.events.clear() -> IntegrityError from schedule_id's NOT NULL. Note the
    #                              mechanism: passive_deletes="all" only governs parent
    #                              *deletes*, so de-associating a child still tries to
    #                              NULL its FK. Loud, and no data lost, which is the
    #                              outcome that matters --- this exact shape used to fire
    #                              delete-orphan and erase a patient's history with no
    #                              db.delete anywhere in the diff.
    #
    # Regeneration retires rows by status instead (see schedule_service.generate_schedules).
    events: Mapped[List["MedicationEvent"]] = relationship(
        "MedicationEvent",
        back_populates="schedule",
        passive_deletes="all",
    )

    # Reminders are notification artefacts, not clinical history: a reminder records
    # that the phone was told to buzz, and the dose it was about is in medication_events.
    # Nothing reviews them after the fact, so these keep ON DELETE CASCADE.
    reminders: Mapped[List["Reminder"]] = relationship(
        "Reminder",
        back_populates="schedule",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def lifecycle_on(self, local_today: date) -> ScheduleLifecycle:
        """
        This schedule's lifecycle state on a given local calendar day.

        Takes the date instead of reading the clock, because "today" is the *patient's*
        today. A schedule stores a wall-clock time and the patient stores an IANA
        timezone; a zero-argument property would have to use the server's date and would
        be wrong by up to a day for anyone not sitting in the server's zone --- the same
        class of bug ``dose_instant_utc`` exists to prevent. Callers already hold the
        patient's local date (``schedule_service.resolve_patient_timezone``).

        A retired status wins over the calendar: a course cancelled halfway through is
        CANCELLED, not COMPLETED, because it did not complete.
        """
        stored = ScheduleLifecycle(self.status)
        if stored is not ScheduleLifecycle.ACTIVE:
            return stored
        if self.end_date is not None and self.end_date < local_today:
            return ScheduleLifecycle.COMPLETED
        return ScheduleLifecycle.ACTIVE
