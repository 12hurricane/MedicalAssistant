from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.user import User

class ConsentRecord(TimestampMixin, Base):
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    consent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    caregiver_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="consents")
    caregiver_user: Mapped["User"] = relationship("User")
