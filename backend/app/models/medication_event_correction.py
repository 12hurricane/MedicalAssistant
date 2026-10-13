from datetime import datetime
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.types import UTCDateTime

class MedicationEventCorrection(TimestampMixin, Base):
    __tablename__ = "medication_event_corrections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("medication_events.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    corrected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    corrected_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    event: Mapped["MedicationEvent"] = relationship("MedicationEvent")
    user: Mapped["User"] = relationship("User")
