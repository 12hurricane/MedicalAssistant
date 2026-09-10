from datetime import date
from typing import List
from sqlalchemy import ForeignKey, String, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON
from app.models.base import Base, TimestampMixin

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
    prescriptions: Mapped[List["Prescription"]] = relationship("Prescription", back_populates="patient")
    medication_events: Mapped[List["MedicationEvent"]] = relationship("MedicationEvent", back_populates="patient")
    consents: Mapped[List["ConsentRecord"]] = relationship("ConsentRecord", back_populates="patient")
    prescribed_medications: Mapped[List["PrescribedMedication"]] = relationship("PrescribedMedication", back_populates="patient")
    schedules: Mapped[List["MedicationSchedule"]] = relationship("MedicationSchedule", back_populates="patient")
    adherence_reports: Mapped[List["AdherenceReport"]] = relationship("AdherenceReport", back_populates="patient")
    reminders: Mapped[List["Reminder"]] = relationship("Reminder", back_populates="patient")
    follow_up_tasks: Mapped[List["FollowUpTask"]] = relationship("FollowUpTask", back_populates="patient")
