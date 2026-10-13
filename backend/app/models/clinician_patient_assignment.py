from datetime import datetime
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.types import UTCDateTime

class ClinicianPatientAssignment(TimestampMixin, Base):
    __tablename__ = "clinician_patient_assignments"
    __table_args__ = (
        UniqueConstraint("clinician_id", "patient_id", name="uq_clinician_patient"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    clinician_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    # Relationships
    clinician: Mapped["User"] = relationship("User", foreign_keys=[clinician_id])
    patient: Mapped["Patient"] = relationship("Patient")
    assigner: Mapped["User"] = relationship("User", foreign_keys=[assigned_by])
