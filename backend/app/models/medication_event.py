import enum
from datetime import datetime
from sqlalchemy import ForeignKey, String, Index, UniqueConstraint, text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.types import UTCDateTime


class MedicationEventStatus(str, enum.Enum):
    PENDING = "PENDING"
    TAKEN = "TAKEN"
    SKIPPED = "SKIPPED"
    MISSED = "MISSED"
    SNOOZED = "SNOOZED"


class SkipReasonCode(str, enum.Enum):
    """
    Closed vocabulary for *why* a dose was skipped, chosen by the patient from a
    fixed list in the UI rather than typed.

    This exists so the barrier classifier stops guessing. Keyword-matching free text
    ("stomach" -> side effects) is a heuristic that is wrong in both directions, and
    its output is presented to a clinician as OBSERVED evidence. A tapped option is
    the patient's actual answer.

    It is also the trust boundary. A value here is one of these constants or the
    write is rejected, so it is safe to render into any downstream context. The
    free-text ``skip_reason`` beside it is arbitrary patient input and is not.
    """

    CLINICIAN_INSTRUCTED = "CLINICIAN_INSTRUCTED"
    SIDE_EFFECTS = "SIDE_EFFECTS"
    UNAVAILABLE = "UNAVAILABLE"
    COST = "COST"
    SCHEDULE_CONFLICT = "SCHEDULE_CONFLICT"
    OTHER = "OTHER"


class MedicationEvent(TimestampMixin, Base):
    __tablename__ = "medication_events"
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_at", name="uq_medication_event_schedule_scheduled_at"),
        Index("ix_medication_events_patient_scheduled", "patient_id", "scheduled_at"),
        Index("ix_medication_events_reminder_id", "reminder_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT, not CASCADE. This row is adherence history and is derived from nothing,
    # so a delete is unrecoverable. One constraint protects the whole chain:
    #
    #   DELETE a medication_schedule       -> refused directly by this FK
    #   DELETE a prescribed_medication     -> refused, because its CASCADE into
    #                                         medication_schedules trips this RESTRICT
    #   DELETE a prescription              -> refused, transitively, same path
    #
    # patient_id stays CASCADE deliberately. Erasing a patient must remain possible ---
    # a hospital cannot be told its data-protection obligations are blocked by a
    # foreign key --- and events cascade from patients on their own FK, so a
    # patient-level delete still succeeds while none of the narrower ones do.
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("medication_schedules.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reminder_id: Mapped[int | None] = mapped_column(
        ForeignKey("reminders.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=MedicationEventStatus.PENDING.value, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(50), default="PATIENT")
    # TRUSTED. One of SkipReasonCode, or NULL. Collected by tapping a fixed option.
    skip_reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # UNTRUSTED patient-authored free text. Never interpolate this into an
    # instruction context; it belongs inside a delimited untrusted block. See
    # app/llm/prompt.py.
    skip_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clinician_confirmed: Mapped[bool] = mapped_column(default=False, server_default=false(), nullable=False)
    verifying_clinician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    snooze_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    # Relationships
    schedule: Mapped["MedicationSchedule"] = relationship("MedicationSchedule", back_populates="events")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="medication_events")
    reminder: Mapped["Reminder | None"] = relationship("Reminder", back_populates="event")

