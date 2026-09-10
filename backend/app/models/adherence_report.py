from datetime import date
from sqlalchemy import ForeignKey, Date, Float, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class AdherenceReport(TimestampMixin, Base):
    __tablename__ = "adherence_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    calculated_score: Mapped[float] = mapped_column(Float, nullable=False)
    identified_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="adherence_reports")
