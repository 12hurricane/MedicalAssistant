from datetime import date
from typing import List, TYPE_CHECKING
from sqlalchemy import ForeignKey, String, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.adherence_report import AdherenceReport
    from app.models.consent import ConsentRecord
    from app.models.follow_up_task import FollowUpTask
    from app.models.medication_event import MedicationEvent
    from app.models.medication_schedule import MedicationSchedule
    from app.models.prescribed_medication import PrescribedMedication
    from app.models.prescription import Prescription
    from app.models.reminder import Reminder
    from app.models.user import User

class Patient(TimestampMixin, Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    emergency_contact: Mapped[str | None] = mapped_column(String, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(10), nullable=True)
    
    # Using JSON type for SQLite compatibility
    allergies: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=[])
    chronic_conditions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=[])
    
    preferred_language: Mapped[str] = mapped_column(String(30), default='en')
    # IANA timezone name (e.g. 'Asia/Kolkata'). Dose times are local to the patient,
    # so reminders must be resolved against this, not the server's clock.
    timezone: Mapped[str] = mapped_column(String(50), default='UTC')

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="patient")
    prescriptions: Mapped[List["Prescription"]] = relationship("Prescription", back_populates="patient", cascade="all, delete-orphan")
    medication_events: Mapped[List["MedicationEvent"]] = relationship("MedicationEvent", back_populates="patient", cascade="all, delete-orphan")
    consents: Mapped[List["ConsentRecord"]] = relationship("ConsentRecord", back_populates="patient", cascade="all, delete-orphan")
    prescribed_medications: Mapped[List["PrescribedMedication"]] = relationship("PrescribedMedication", back_populates="patient", cascade="all, delete-orphan")
    schedules: Mapped[List["MedicationSchedule"]] = relationship("MedicationSchedule", back_populates="patient", cascade="all, delete-orphan")
    adherence_reports: Mapped[List["AdherenceReport"]] = relationship("AdherenceReport", back_populates="patient", cascade="all, delete-orphan")
    reminders: Mapped[List["Reminder"]] = relationship("Reminder", back_populates="patient", cascade="all, delete-orphan")
    follow_up_tasks: Mapped[List["FollowUpTask"]] = relationship("FollowUpTask", back_populates="patient", cascade="all, delete-orphan")

    @property
    def name(self) -> str | None:
        return self.user.name if "user" in self.__dict__ and self.user else None

    @property
    def email(self) -> str | None:
        return self.user.email if "user" in self.__dict__ and self.user else None
