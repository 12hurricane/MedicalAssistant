from typing import List, TYPE_CHECKING
from sqlalchemy import ForeignKey, String, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.medication import Medication
    from app.models.medication_schedule import MedicationSchedule
    from app.models.patient import Patient
    from app.models.prescription import Prescription

class PrescribedMedication(TimestampMixin, Base):
    __tablename__ = "prescribed_medications"

    id: Mapped[int] = mapped_column(primary_key=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    medicine_name: Mapped[str] = mapped_column(String(200), nullable=False)
    strength: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dose: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frequency: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional link to the drug catalogue. Nullable because OCR gives free text first;
    # it is resolved to a catalogue entry during verification.
    medication_id: Mapped[int | None] = mapped_column(
        ForeignKey("medications.id"), nullable=True
    )

    # Relationships
    prescription: Mapped["Prescription"] = relationship("Prescription", back_populates="medications")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="prescribed_medications")
    medication: Mapped["Medication | None"] = relationship("Medication")
    # passive_deletes lets the DB's ON DELETE CASCADE do the work. Without it,
    # SQLAlchemy would try to NULL out schedules.prescribed_medication_id on delete,
    # which is NOT NULL, and the corrections path would fail with an IntegrityError.
    #
    # That CASCADE no longer reaches adherence history: medication_events.schedule_id is
    # ON DELETE RESTRICT, so deleting a prescribed medication that has logged doses is
    # refused by the database rather than cascading two levels down and erasing them.
    # Discontinuing a medication is `is_active = False` plus a CANCELLED status on its
    # schedules (see schedule_service.generate_schedules), never a delete.
    schedules: Mapped[List["MedicationSchedule"]] = relationship(
        "MedicationSchedule",
        back_populates="prescribed_medication",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
