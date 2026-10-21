from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.medication_schedule import MedicationSchedule

class ScheduleVersion(TimestampMixin, Base):
    __tablename__ = "schedule_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("medication_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    schedule_data: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Relationships
    schedule: Mapped["MedicationSchedule"] = relationship("MedicationSchedule")
