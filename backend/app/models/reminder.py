import enum
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.medication_event import MedicationEvent
    from app.models.medication_schedule import MedicationSchedule
    from app.models.patient import Patient


class ReminderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class Reminder(TimestampMixin, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_reminder_schedule_scheduled_for"),
        Index("ix_reminders_status_scheduled_for", "status", "scheduled_for"),
        Index("ix_reminders_patient_scheduled_for", "patient_id", "scheduled_for"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("medication_schedules.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    channel: Mapped[str] = mapped_column(String(30), default="PUSH")
    status: Mapped[str] = mapped_column(String(30), default=ReminderStatus.PENDING.value)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    schedule: Mapped["MedicationSchedule"] = relationship("MedicationSchedule", back_populates="reminders")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="reminders")
    event: Mapped["MedicationEvent | None"] = relationship("MedicationEvent", back_populates="reminder", uselist=False)

