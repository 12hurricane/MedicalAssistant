from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.user import User

class FollowUpTask(TimestampMixin, Base):
    __tablename__ = "follow_up_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default='MEDIUM')
    status: Mapped[str] = mapped_column(String(30), default='OPEN')
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="follow_up_tasks")
    assigned_user: Mapped["User"] = relationship("User")
