from datetime import date, datetime
from typing import List
from sqlalchemy import ForeignKey, String, Date, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.types import UTCDateTime

class Prescription(TimestampMixin, Base):
    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    clinic_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prescription_date: Mapped[date] = mapped_column(Date, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), default='PENDING')
    # Audit trail: who signed off on this prescription and when.
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="prescriptions")
    medications: Mapped[List["PrescribedMedication"]] = relationship(
        "PrescribedMedication",
        back_populates="prescription",
        cascade="all, delete-orphan",
    )
    verified_user: Mapped["User"] = relationship("User")
